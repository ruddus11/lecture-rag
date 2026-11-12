from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.retrieval.embeddings.base import EmbeddingError, model_slug
from app.retrieval.embeddings.cache import EmbeddingFileCache
from app.retrieval.embeddings.openai_emb import OpenAIEmbedding
from app.retrieval.vector import collection_name
from tests.fakes import FakeEmbedder


def test_collection_naming():
    assert model_slug("BAAI/bge-m3") == "bge_m3"
    assert collection_name("BAAI/bge-m3", 1024) == "chunks__bge_m3__1024"
    assert collection_name("text-embedding-3-small", 1536) == "chunks__text_embedding_3_small__1536"
    assert collection_name("intfloat/multilingual-e5-small", 384) == "chunks__multilingual_e5_small__384"


def test_file_cache_hits_and_layout(tmp_path):
    emb = FakeEmbedder(dim=8)
    cache = EmbeddingFileCache(tmp_path, emb)
    first = cache.embed_documents(["가나다", "라마바", "가나다"])
    assert cache.misses == 3 and emb.calls == 1
    files = list((tmp_path / "fake_embed").rglob("*.npy"))
    assert len(files) == 2 and all(f.parent.name == f.stem[:2] for f in files)
    again = EmbeddingFileCache(tmp_path, emb).embed_documents(["라마바", "가나다"])  # 재시작 후
    assert emb.calls == 1
    for got, want in zip(again, [first[1], first[0]], strict=True):
        assert got == pytest.approx(want, abs=1e-6)  # float32 저장


def test_file_cache_corrupt_file_is_miss(tmp_path):
    emb = FakeEmbedder(dim=8)
    cache = EmbeddingFileCache(tmp_path, emb)
    cache.embed_documents(["abc"])
    for f in (tmp_path / "fake_embed").rglob("*.npy"):
        f.write_bytes(b"garbage")
    cache.embed_documents(["abc"])
    assert emb.calls == 2


class _FakeOpenAIClient:
    def __init__(self, fail_times: int = 0, exc: Exception | None = None) -> None:
        self.batches: list[int] = []
        self.fail_times = fail_times
        self.exc = exc
        self.embeddings = SimpleNamespace(create=self._create)

    def _create(self, model: str, input: list[str]):
        if self.fail_times:
            self.fail_times -= 1
            assert self.exc is not None
            raise self.exc
        self.batches.append(len(input))
        data = [SimpleNamespace(index=i, embedding=[float(i), 1.0]) for i in range(len(input))]
        return SimpleNamespace(data=list(reversed(data)))


def _rate_limit_error():
    import httpx
    import openai

    resp = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com/v1/embeddings"))
    return openai.RateLimitError("rate limited", response=resp, body=None)


def test_openai_batches_of_100_and_order(monkeypatch):
    emb = OpenAIEmbedding("sk-test", "text-embedding-3-small")
    emb._client = _FakeOpenAIClient()
    out = emb.embed_documents([f"t{i}" for i in range(250)])
    assert emb._client.batches == [100, 100, 50]
    assert out[0] == [0.0, 1.0] and out[99] == [99.0, 1.0] and out[100] == [0.0, 1.0]
    assert emb.dim == 1536


def test_openai_backoff_then_rate_limited(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _s: None)
    err = _rate_limit_error()
    emb = OpenAIEmbedding("sk-test")
    emb._client = _FakeOpenAIClient(fail_times=2, exc=err)  # 2번 429 후 성공
    assert emb.embed_query("q") == [0.0, 1.0]
    emb._client = _FakeOpenAIClient(fail_times=10, exc=err)  # 3회 backoff 후 포기
    with pytest.raises(EmbeddingError) as ei:
        emb.embed_query("q")
    assert ei.value.code == "embedding_rate_limited"

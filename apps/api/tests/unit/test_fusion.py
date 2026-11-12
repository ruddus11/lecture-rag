from __future__ import annotations

import pytest

from app.retrieval.fusion import cap_per_page, rrf
from app.retrieval.types import Candidate, ChunkDoc


def C(cid: str, rank: int, doc: str = "d1", page: int = 1) -> Candidate:
    return Candidate(ChunkDoc(cid, doc, "c", "i", 1, page, 0, cid), rank, 0.0)


def test_rrf_scores_sum_both_engines():
    out = rrf([C("a", 1), C("b", 2)], [C("b", 1), C("c", 2)], k=60)
    by = {f.chunk.chunk_id: f for f in out}
    assert by["b"].score == pytest.approx(1 / 62 + 1 / 61)
    assert by["a"].score == pytest.approx(1 / 61) and by["c"].score == pytest.approx(1 / 62)
    assert [f.chunk.chunk_id for f in out] == ["b", "a", "c"]
    assert (by["b"].keyword_rank, by["b"].vector_rank) == (2, 1)
    assert (by["a"].keyword_rank, by["a"].vector_rank) == (1, None)


def test_rrf_tie_break_vector_first_then_chunk_id():
    # a: keyword 1위만, z: vector 1위만 → 같은 점수. vector rank 가 있는 z 가 앞.
    out = rrf([C("a", 1), C("m", 2)], [C("z", 1), C("b", 2)])
    assert [f.chunk.chunk_id for f in out] == ["z", "a", "b", "m"]
    # 같은 엔진 조건의 동점은 chunk_id 사전순
    out = rrf(None, [C("y", 1)]) + rrf(None, [C("x", 1)])
    assert (
        sorted(out, key=lambda f: (-f.score, f.vector_rank is None, f.chunk.chunk_id))[0].chunk.chunk_id
        == "x"
    )


def test_rrf_one_side_missing_and_duplicates():
    assert [f.chunk.chunk_id for f in rrf(None, [C("v1", 1), C("v2", 2)])] == ["v1", "v2"]
    assert [f.chunk.chunk_id for f in rrf([C("k1", 1)], [])] == ["k1"]
    out = rrf([C("a", 1), C("a", 3)], [C("a", 2)])  # 같은 엔진 안 중복은 최상위 rank 만
    assert len(out) == 1 and out[0].score == pytest.approx(1 / 61 + 1 / 62) and out[0].keyword_rank == 1
    assert rrf(None, None) == []


def test_cap_per_page():
    items = rrf(
        None,
        [
            C("a", 1, page=1),
            C("b", 2, page=1),
            C("c", 3, page=1),
            C("d", 4, page=2),
            C("e", 5, doc="d2", page=1),
        ],
    )
    assert [f.chunk.chunk_id for f in cap_per_page(items, 2)] == ["a", "b", "d", "e"]
    assert [f.chunk.chunk_id for f in cap_per_page(items, 1)] == ["a", "d", "e"]

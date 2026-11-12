from app.core.cache import CacheStore, embedding_key, retrieval_key


def test_embedding_key_normalizes_and_separates_models():
    assert embedding_key("model", " A  B ") == embedding_key("model", "A B")
    assert embedding_key("model", "A B") != embedding_key("other", "A B")


def test_retrieval_key_separates_scope_and_profile():
    args = ["query", "hybrid", 30, 6, 60, 2, "bge", "korean", "scope-a-v1"]
    baseline = retrieval_key(*args)
    for index, replacement in [(1, "vector"), (6, "e5"), (7, "standard"), (8, "scope-b-v1")]:
        other = args.copy()
        other[index] = replacement
        assert retrieval_key(*other) != baseline


def test_zero_ttl_and_clear():
    disabled = CacheStore()
    disabled.retrieval["key"] = ["hit"]
    assert disabled.retrieval.get("key") is None
    enabled = CacheStore(60, 60)
    enabled.retrieval["key"] = ["hit"]
    enabled.embeddings["key"] = [1.0]
    enabled.clear()
    assert not enabled.retrieval and not enabled.embeddings

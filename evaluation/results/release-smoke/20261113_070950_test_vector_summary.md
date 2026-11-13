# 검색 평가

```json
{
  "mode": "vector",
  "n": 10,
  "failed": 0,
  "skipped": 0,
  "hit_1": 1.0,
  "hit_3": 1.0,
  "hit_5": 1.0,
  "mrr_10": 1.0,
  "required_recall_5": 1.0,
  "environment": {
    "version": "0.1.0",
    "commit": "unknown",
    "embedding": {
      "provider": "local",
      "model": "BAAI/bge-m3",
      "dim": 1024
    },
    "answer": {
      "provider": "openai",
      "model": "gpt-4.1-mini"
    },
    "index_profile": {
      "id": "local:bge_m3:1024|chunks_v1|chunker-v1|pymupdf-v1",
      "qdrant_collection": "chunks__bge_m3__1024",
      "opensearch_index": "chunks_v1"
    },
    "keyword_analyzer": "korean",
    "chunker_version": "v1",
    "parser_version": "pymupdf-v1",
    "document_count": 2,
    "chunk_count": 19,
    "container_memory": "API limit 4GiB; point-in-time usage 2.23GiB",
    "environment": "Docker Desktop arm64; local bge-m3; cache off",
    "cache": "off"
  }
}
```

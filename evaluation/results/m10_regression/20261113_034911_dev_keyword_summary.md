# 검색 평가

```json
{
  "mode": "keyword",
  "n": 30,
  "failed": 0,
  "skipped": 0,
  "hit_1": 0.9615384615384616,
  "hit_3": 1.0,
  "hit_5": 1.0,
  "mrr_10": 0.9807692307692307,
  "required_recall_5": 1.0,
  "environment": {
    "version": "0.1.0",
    "commit": "7f77d4a",
    "embedding": {
      "provider": "local",
      "model": "BAAI/bge-m3",
      "dim": 1024
    },
    "answer": {
      "provider": "fake",
      "model": "fake"
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
    "container_memory": "unavailable (native host)",
    "environment": "macOS arm64 Apple M5 24GB; native Qdrant 1.20.0 OpenSearch 2.19.7 Nori; bge-m3 CPU; 3 sample docs only",
    "cache": "off"
  }
}
```

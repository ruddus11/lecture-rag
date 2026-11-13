# 지연 측정

```json
{
  "label": "after_cache",
  "endpoint": "search",
  "mode": "hybrid",
  "split": "dev",
  "warmup": 10,
  "distinct_queries": 30,
  "n": 200,
  "concurrency": 1,
  "errors": 0,
  "error_rate": 0.0,
  "error_kinds": {},
  "client_ms": {
    "n": 200,
    "p50": 1.22,
    "p95": 45.4
  },
  "server_ms": {
    "embed_query": {
      "n": 20,
      "p50": 41.0,
      "p95": 70.7
    },
    "fusion": {
      "n": 20,
      "p50": 0.0,
      "p95": 0.0
    },
    "keyword": {
      "n": 20,
      "p50": 1.4,
      "p95": 1.8
    },
    "ledger_check": {
      "n": 200,
      "p50": 0.1,
      "p95": 0.3
    },
    "scope": {
      "n": 200,
      "p50": 0.1,
      "p95": 0.4
    },
    "total": {
      "n": 200,
      "p50": 0.2,
      "p95": 43.8
    },
    "vector": {
      "n": 20,
      "p50": 2.3,
      "p95": 3.8
    }
  },
  "throughput_rps": 156.91,
  "cache_status": {
    "miss": 20,
    "hit": 180
  },
  "api_rss_mb": {
    "max": 2147.8,
    "end": 2147.8
  },
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
    "environment": "macOS arm64 Apple M5 24GB; native Qdrant 1.20.0 OpenSearch 2.19.7 Nori; bge-m3 CPU; fake answer",
    "cache": "embed=3600s retrieval=300s",
    "client_host": "Darwin arm64 python 3.12.13",
    "measured_at": "2026-11-13T03:47:54+00:00"
  }
}
```

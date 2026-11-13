# 지연 측정

```json
{
  "label": "after_parallel",
  "endpoint": "answers",
  "mode": "hybrid",
  "split": "dev",
  "warmup": 3,
  "distinct_queries": 30,
  "n": 40,
  "concurrency": 1,
  "errors": 0,
  "error_rate": 0.0,
  "error_kinds": {},
  "client_ms": {
    "n": 40,
    "p50": 46.83,
    "p95": 52.05
  },
  "server_ms": {
    "generation": {
      "n": 40,
      "p50": 0.0,
      "p95": 0.0
    },
    "retrieval": {
      "n": 40,
      "p50": 44.7,
      "p95": 49.6
    },
    "total": {
      "n": 40,
      "p50": 44.8,
      "p95": 49.6
    },
    "verify": {
      "n": 40,
      "p50": 0.0,
      "p95": 0.0
    }
  },
  "throughput_rps": 21.03,
  "cache_status": {
    "off": 40
  },
  "api_rss_mb": {
    "max": 1975.7,
    "end": 1975.7
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
    "cache": "off",
    "client_host": "Darwin arm64 python 3.12.13",
    "measured_at": "2026-11-13T03:47:10+00:00"
  }
}
```

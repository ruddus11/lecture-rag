# 지연 측정

```json
{
  "label": "after_parallel",
  "endpoint": "search",
  "mode": "hybrid",
  "split": "dev",
  "warmup": 10,
  "distinct_queries": 30,
  "n": 200,
  "concurrency": 5,
  "errors": 0,
  "error_rate": 0.0,
  "error_kinds": {},
  "client_ms": {
    "n": 200,
    "p50": 117.71,
    "p95": 126.48
  },
  "server_ms": {
    "embed_query": {
      "n": 200,
      "p50": 106.8,
      "p95": 120.7
    },
    "fusion": {
      "n": 200,
      "p50": 0.0,
      "p95": 0.0
    },
    "keyword": {
      "n": 200,
      "p50": 1.7,
      "p95": 2.5
    },
    "ledger_check": {
      "n": 200,
      "p50": 0.2,
      "p95": 0.4
    },
    "scope": {
      "n": 200,
      "p50": 0.3,
      "p95": 0.5
    },
    "total": {
      "n": 200,
      "p50": 114.3,
      "p95": 124.2
    },
    "vector": {
      "n": 200,
      "p50": 5.5,
      "p95": 6.7
    }
  },
  "throughput_rps": 42.71,
  "cache_status": {
    "off": 200
  },
  "api_rss_mb": {
    "max": 1975.6,
    "end": 1975.6
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
    "measured_at": "2026-11-13T03:47:08+00:00"
  }
}
```

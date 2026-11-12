# 인수인계 (handoff)

## 되는 흐름

(마일스톤 진행에 따라 갱신)

## 미완료

(마일스톤 진행에 따라 갱신)

## 마지막 실행 명령·결과

(마일스톤 진행에 따라 갱신)

## 실행 로그

### M3 재시작 복구 수동 확인 (2026-11-12, 로컬 uvicorn + Qdrant 1.20.0 바이너리, bge-m3)

81쪽 PDF를 `ai_basics`에 올리고 작업이 `stage=embedding`일 때 `kill -9`로 API를 죽인 뒤 다시 띄웠다.

```text
{"status": "processing", "stage": "embedding", "attempts": 1, ...}          # 강제 종료 직전 GET /jobs/{id}
sqlite> select status, stage, attempts from ingestion_jobs → processing|embedding|1   # 종료 직후 원장
{"level": "WARNING", "event": "jobs_recovered", "count": 1}                  # 재기동 lifespan
{"event": "job_finished", "kind": "ingest", "stage_ms": {"parsing": 44.9, "chunking": 30.1, "embedding": 15839.5, "indexing_vector": 31.4, "activating": 6.9}, "ms": 15957.1}
{"status": "succeeded", "stage": "activating", "attempts": 2, ...}           # 재기동 후 GET /jobs/{id}
```

같은 흐름은 `tests/api/test_documents.py::test_restart_recovery_requeues_processing`로 자동 검증한다.

### M4 vector 검색 수동 확인 (2026-11-12, `python -m scripts.e2e_smoke --modes vector`)

자작 샘플 3종(`data/samples/`) 색인 후 샘플 질문 5개 중 5개가 기대 페이지를 상위 5 안에 반환(1위 4개, 2위 1개). b_student 질문(TCP 느린 시작)은 campus_b 문서만 반환. `/health/ready`: `qdrant_collection=chunks__bge_m3__1024`, `qdrant_payload_indexes=[collection_id, document_id, document_version, institution_id]`. 전체 출력은 `docs/logs/m4_e2e_vector.jsonl`.

## 알려진 문제

- 구현 머신에 Docker가 없다. compose 기동·이미지 빌드·실제 Qdrant/OpenSearch 연동은 Docker 환경에서 처음 확인해야 한다.

## 다음 한 작업

(마일스톤 진행에 따라 갱신)

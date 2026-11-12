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

### M5 세 모드·부분 장애 수동 확인 (2026-11-12, bge-m3 + Qdrant 1.20.0 + OpenSearch 2.19.7/nori 네이티브, `infra/local/`)

- `/health/ready` 200: `sqlite, qdrant, opensearch, nori, embedding_model` 모두 true, `qdrant_payload_indexes` 4개.
- 샘플 질문 5개 hit@5: keyword 5/5, vector 5/5, hybrid 5/5. hybrid `modes_used=["keyword","vector"]`. 출력 `docs/logs/m5_e2e_three_modes.jsonl`.
- OpenSearch 프로세스 종료 상태: `/health/ready` 503(`opensearch:false`), hybrid 5건 모두 `degraded=true, modes_used=["vector"]`(hit 5/5), keyword 5건 모두 503 `search_unavailable`. 재기동 후 hybrid `degraded=false` 5/5. 출력 `docs/logs/m5_opensearch_stop.txt`.
- integration: `pytest -m integration` 4 passed (Qdrant payload index·필터·삭제, ingest→3모드→삭제→0건, OpenSearch 중단 시 degraded, Nori 분석).

## 알려진 문제

- 구현 머신에 Docker가 없다. compose 기동·이미지 빌드는 Docker 환경에서 처음 확인해야 한다. 엔진 연동은 같은 버전의 네이티브 바이너리(`infra/local/`)로 확인했다.
- 저장소가 iCloud 동기화 중인 Desktop 아래에 있다. 수 GB의 모델·엔진·가상환경이 업로드되며 파일 읽기가 크게 느려져서, `.tools`·`apps/api/.venv`·`apps/web/node_modules`의 실제 폴더를 `*.nosync`(iCloud 제외 이름)로 바꾸고 원래 이름은 심볼릭 링크로 두었다. 되돌리려면 링크를 지우고 폴더 이름을 원래대로 바꾸면 된다.

## 다음 한 작업

(마일스톤 진행에 따라 갱신)

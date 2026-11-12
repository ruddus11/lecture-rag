# 인수인계 (handoff)

## 되는 흐름

로그인→업로드→ready→질문→근거 카드→인증 PDF 페이지 뷰어, 보류 화면까지 로컬 실제 엔진에서 확인.

## 미완료

M8 삭제·재시도·캐시 골격 및 기관 격리 회귀. Docker 실기동과 유료 provider smoke는 미검증.

## 마지막 실행 명령·결과

M7: API pytest 112 passed, ruff·mypy 통과. 웹 최종 검증은 아래 M7 로그 참조.

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

### M6 답변 수동 확인 (2026-11-12, fake provider, 실제 엔진 + bge-m3)

`e2e_smoke --skip-upload --modes hybrid --answers`: 샘플 질문 5개 모두 200, `abstained=false`, 인용 페이지가 기대 페이지와 일치(5/5). fake provider는 첫 근거의 첫 문장을 답으로 쓰므로 답변 품질의 증거가 아니다. 출력 `docs/logs/m6_e2e_answers_fake.jsonl`. 실제 OpenAI·Claude 호출은 키가 없어 미실행.

## 알려진 문제

- 구현 머신에 Docker가 없다. compose 기동·이미지 빌드는 Docker 환경에서 처음 확인해야 한다. 엔진 연동은 같은 버전의 네이티브 바이너리(`infra/local/`)로 확인했다.
- 저장소가 iCloud 동기화 중인 Desktop 아래에 있다. 수 GB의 모델·엔진·가상환경이 업로드되며 파일 읽기가 크게 느려져서, `.tools`·`apps/api/.venv`·`apps/web/node_modules`의 실제 폴더를 `*.nosync`(iCloud 제외 이름)로 바꾸고 원래 이름은 심볼릭 링크로 두었다. 되돌리려면 링크를 지우고 폴더 이름을 원래대로 바꾸면 된다.

## 다음 한 작업

M8 삭제·재시도 API와 워커 구현 및 회귀 검증.

### M7 웹 흐름 (2026-11-12, Chrome headless + 실제 로컬 엔진)

`cd apps/web && node e2e/browser_flow.mjs ../../data/samples/os_week3_process.pdf ../../docs/screenshots/m7` 통과: login_ok → upload_ready(2초) → answer_ok → viewer_ok(3 / 3쪽) → abstain_ok.

스크린샷: [로그인](screenshots/m7/01_login.png), [업로드 완료](screenshots/m7/02_documents_ready.png), [답변](screenshots/m7/03_answer.png), [PDF 페이지](screenshots/m7/04_pdf_page.png), [보류](screenshots/m7/05_abstain.png).

계정 변경 중 응답을 지연시킨 회귀 테스트로 기존 문서 캐시 노출을 재현(RED)하고 인증 세션마다 QueryClient를 교체하여 수정했다. 브라우저 최초 실패는 로그인 입력 시 개발서버 갱신으로 아이디가 비워진 것으로 확인했으며 networkidle 후 실제 키 입력으로 안정화했다.

M7 최종: 웹 13 tests passed, typecheck·eslint·build 통과. `.tools/bin/docker-compose --env-file .env.example config --quiet` 통과.

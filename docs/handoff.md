# 인수인계 (handoff)

## 되는 흐름

로그인→업로드→ready→질문→근거 카드→인증 PDF 페이지 뷰어, 보류 화면까지 로컬 실제 엔진에서 확인.

## 미완료

이 브랜치 M11은 구현·로컬 검증 완료. M12 CI/문서는 구현했으나 원격 CI 녹색·Linux Compose·fresh clone 전체 명령 게이트 미완료. M8 수용·태그·M10은 main 담당. 유료 smoke는 키가 없어 SKIP.

## 마지막 실행 명령·결과

M11 ccdcd0e: API 136 passed + scanner 1 passed, ruff·format·mypy·웹 build·Compose config 통과. M12 fresh clone(ff0f3ec 소스): API 137 passed/5 deselected, 웹 16 passed, Node 22.23.5 engine warning 0건, lint·format·mypy·typecheck·build·standalone Compose config 통과. 로그: docs/logs/m12_fresh_local.txt, 상세: docs/reproducibility.md. 아래 이전 실행 기록은 당시 소스·환경의 결과다.

### 이전 실행 로그

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

main에 M11/M12 병합 후 M10 캐시와 고객 수용 회귀를 재실행하고, 승인된 원격 환경에서 CI 수동 integration job을 실행해 Linux 증거를 남긴다. 이 워크트리에서는 push·태그를 수행하지 않는다.

### M7 웹 흐름 (2026-11-12, Chrome headless + 실제 로컬 엔진)

`cd apps/web && node e2e/browser_flow.mjs ../../data/samples/os_week3_process.pdf ../../docs/screenshots/m7` 통과: login_ok → upload_ready(2초) → answer_ok → viewer_ok(3 / 3쪽) → abstain_ok.

스크린샷: [로그인](screenshots/m7/01_login.png), [업로드 완료](screenshots/m7/02_documents_ready.png), [답변](screenshots/m7/03_answer.png), [PDF 페이지](screenshots/m7/04_pdf_page.png), [보류](screenshots/m7/05_abstain.png).

계정 변경 중 응답을 지연시킨 회귀 테스트로 기존 문서 캐시 노출을 재현(RED)하고 인증 세션마다 QueryClient를 교체하여 수정했다. 브라우저 최초 실패는 로그인 입력 시 개발서버 갱신으로 아이디가 비워진 것으로 확인했으며 networkidle 후 실제 키 입력으로 안정화했다.

M7 최종: 웹 13 tests passed, typecheck·eslint·build 통과. `.tools/bin/docker-compose --env-file .env.example config --quiet` 통과.

### M8 구현·검증 (2026-11-12)

삭제는 즉시 deleting으로 차단하고 인덱스→파일→chunks를 정리한다. 실패한 삭제는 재시도할 수 있으며 재시작 복구도 검증했다. 수집 대기 중 삭제 시 상태 역전과 LLM 생성 대기 중 삭제 시 오래된 답변 노출을 각각 RED→GREEN 회귀 테스트로 수정했다.

`uv run pytest -m integration` → 5 passed (실제 로컬 Qdrant/OpenSearch, fake 임베딩). API 삭제 경로를 통해 ingest→3모드→논리 삭제 직후 차단→워커 물리 삭제→0건을 검증했고, retry 후 버전 1 양쪽 엔진 0건·버전 2 적재를 확인했다. aiohttp의 Python 3.12.13 관련 DeprecationWarning 5개는 실패가 아니다.

웹 13 tests, typecheck·eslint·build 통과. `docker compose config`(standalone) 통과. Docker daemon 부재로 fresh compose와 v0.1 태그를 미완료로 남긴다. 설계서 16장 완료 게이트에 따라 M9 이후는 진행하지 않는다.

최종 리뷰 수정: PDF 401은 인증 해제, 503은 표준 오류 요청 ID·재시도 표시. 업로드 네트워크 오류 재시도는 동일 Idempotency-Key 유지. DELETE는 status=deleting, 동일 기관 권한자의 반복 삭제는 409, 타 기관은 404. 최종 웹 16 tests passed, typecheck·eslint·build 통과. API 122 passed. 최종 UI 브라우저 재검증 스크린샷은 `screenshots/m8/`이며 기존 M7 API 프로세스를 사용했다. M8 새 서버 코드는 API/integration에서 별도 검증했다.

M8 최종 검증: API 122 passed(39.44초), 실제 엔진 integration 5 passed(14.27초), 웹 16 passed. ruff check·format(94 files)·mypy·typecheck·eslint·build·compose config 통과. Docker fresh 검증 미실행.

### M9 이어가기 (2026-11-12)

Docker CLI 없음 → fresh compose와 v0.1 보류(ADR-010). 로컬 API 8010 캐시 off, 실제 bge-m3/Qdrant/Nori로 dev 30문항×3모드 실행, 실패/skip 0. CSV는 evaluation/results. pytest 127 passed, 5 deselected; npm build·standalone compose config 통과. 근거 재확인이 반복 방문의 핵심이며 평가도 정답 페이지 검색을 우선한다. test 10문항 동결. 수동 인용 의미 평가는 남음.

### M11 분리 구현 (2026-11-13)

`uv run pytest`: 136 passed, 5 deselected. 추가한 scanner 회귀는 별도 1 passed. ruff check·format·mypy·npm build·standalone Compose config 통과. `python3 scripts/check_secrets.py --history`: 261 blobs, 0 findings. 중첩 로그·traceback 비밀 마스킹과 HTTP 본문 한도 추가. 설정 변경 3건 수용 테스트 통과. `git config core.hooksPath .githooks`로 비밀 스캔 훅 활성화 가능. M8 수용·태그·M10은 main 담당 범위다.

# 강의자료 RAG 검색

한국어 강의 PDF에서 질문의 근거를 찾고 원문 페이지로 확인하는 검색 서비스다. 반복 학습 중 개념과 출처를 다시 확인하는 흐름에 집중한다. FastAPI·React/TypeScript·Qdrant·OpenSearch의 BM25/vector/RRF hybrid를 비교할 수 있다.

## 현재 상태

M1~M9 구현과 로컬 검증 기록이 있으며, 이 브랜치는 M11 보안·M12 CI/재현 문서를 추가한다. M8 fresh Compose·v0.1 태그·M10 성능은 main 담당 범위다. 원격 CI·Linux Compose 성공은 아직 미검증이다. 정확한 결과와 남은 항목은 [진행보고](docs/구현_진행보고.md), [작업목록](docs/구현_작업목록.md), [handoff](docs/handoff.md) 참조.

## 실행

Python 3.12, Docker Compose v2, Docker Desktop 메모리 최소 8GB와 충분한 디스크가 필요하다. Linux에서는 vm.max_map_count=262144 이상을 설정한다. 첫 실행은 모델 다운로드에 시간이 걸린다.

```bash
python3 scripts/prepare_env.py
# 기존 .env가 있으면 보존하고 AUTH_SECRET을 32바이트 이상 난수로 직접 설정한다.
# 기관·계정 파일이 없으면 SEED_ON_START=true일 때 example 파일을 읽는다.
docker compose up --build -d
docker compose ps
curl http://localhost:8000/api/v1/health/ready
```

웹: http://localhost:3000. API: http://localhost:8000/api/v1/docs. 키 없이 `EMBEDDING_PROVIDER=local`, `EMBEDDING_MODEL=BAAI/bge-m3`, `ANSWER_PROVIDER=fake`가 기본이다. fake는 동작 검증용이며 생성 모델의 답변 품질을 보여주지 않는다.

| 데모 계정 | 비밀번호 | 권한 |
|---|---|---|
| a_admin | admin-a-demo-2026 | campus_a 관리자 |
| a_student | student-a-demo-2026 | campus_a 학생 |
| b_admin | admin-b-demo-2026 | campus_b 관리자 |
| b_student | student-b-demo-2026 | campus_b 학생 |

로그인 → 관리자 자료 업로드 → 사용 가능 상태 → 질문 → 근거 카드 → PDF 페이지 확인. 실패 문서는 재시도, 불필요한 문서는 삭제할 수 있다. 토큰은 메모리에만 보관하므로 새로고침하면 다시 로그인한다.

## 환경변수

전체 목록은 [.env.example](.env.example). `AUTH_SECRET`, `DATA_DIR`, `INSTITUTIONS_FILE`, `USERS_FILE`, `QDRANT_URL`, `OPENSEARCH_URL`로 실행 환경을 설정한다. 외부 LLM은 `ANSWER_PROVIDER=openai|claude`와 해당 API 키·모델 ID를 설정한다. 실제 유료 API smoke는 키가 없어 미검증이다. 실제 비밀은 `.env`에만 보관한다. 캐시 키·TTL 골격은 있으며 실제 검색 캐시 연결은 M10 범위다.

## 로컬 개발과 검증

Python 3.12, uv 0.11.6, Node.js 22.23.5가 기준이다. Docker 없는 macOS 검증 방법은 [로컬 엔진 안내](infra/local/README.md).

```bash
cd apps/api
uv sync --locked
uv run pytest
uv run ruff check .
uv run mypy app
# 저장소 루트에서 연 별도 터미널
cd apps/web
npm ci
npm run dev
npm run typecheck
npm test
npm run lint
npm run build
```

Vite 프록시는 API 8000으로 연결한다. 실제 엔진 integration은 `cd apps/api && uv run pytest -m integration`. Chrome 브라우저 시나리오는 `apps/web/e2e/browser_flow.mjs` 참조. 기존 컬렉션에 동일 파일을 중복 업로드하면 409이므로 새 자작 PDF나 비어 있는 테스트 컬렉션을 사용한다.

## 구조와 선택 이유

- `apps/api/app`: 인증·권한, SQLite 원장, 문서 단일 워커, retrieval, generation.
- `apps/web/src`: app, features, shared. 서버 상태는 React Query, 인증은 React 메모리 상태.
- `infra/`, `compose.yaml`: 검색 엔진과 네 서비스 구성.
- `config/`: 기관·정적 데모 계정 example.
- `docs/`: 설계·작업목록·ADR·검증 기록.
- `evaluation/`: 동결 dev/test JSONL·HTTP 평가 도구·결과 CSV. 수업 자료는 `evaluation/private/`에만 둔다.

혼자 운영할 수 있도록 SQLite·파일 볼륨·단일 프로세스 큐를 사용한다. 삭제는 원장을 먼저 `deleting`으로 바꿔 접근을 차단한 후 인덱스→파일→청크를 정리한다. 중간 실패는 비공개 상태로 유지하고 관리자가 재시도한다.

## 한계

- 텍스트 PDF만 지원. 스캔·표·다단 레이아웃은 품질 저하 또는 실패.
- 단일 프로세스·단일 워커. 동시 업로드는 직렬 처리.
- 로컬 임베딩은 CPU라 색인이 느리다. 측정 조건은 docs/performance.md 참조.
- 평가 표본이 작아 일반적 우월성을 주장하지 않는다. M9 dev 30문항 결과만 있으며 test 10문항과 실제 생성 모델 품질은 미검증.
- 데모 인증은 정적 계정·HS256 JWT. 공개 배포에는 별도 인증·TLS 필요.
- OpenSearch 보안 플러그인을 끄고 내부 네트워크에만 둔다. 외부 공개 금지.
- 외부 LLM을 선택하면 질문과 검색 근거가 해당 제공자에 전송된다. 개인정보·내부 문서를 반입하지 않는다.
- reranker·Ollama·OCR·Spring gateway는 미구현.

## 다음 작업

main 담당자가 M8 수용·M10 검증을 끝내면 이 브랜치를 병합하고 전체 회귀를 재실행한다. 이후 사용자가 원격 업로드를 승인한 환경에서 Actions 수동 integration job을 실행해 Linux 증거를 첨부한다. 데이터 삭제를 수반하는 `docker compose down -v`는 검증용 환경에서만 실행한다.


## 검증 결과와 화면

| 날짜 / 소스 기준 | 환경 / 표본 | 결과와 증거 |
|---|---|---|
| 2026-11-12 / aa10978 이전 M7 API와 M8 최종 UI | macOS·Chrome, 핵심 흐름 1회 | 로그인→업로드→답변→PDF→보류. [스크린샷 폴더](docs/screenshots/m8/), 새 M11 코드의 브라우저 검증은 아님 |
| 2026-11-12 / 062ede3 M9 | 실제 bge-m3·Qdrant·OpenSearch/Nori, dev 30문항×3모드 | 정답 있음 26문항 Hit@1 keyword 0.9615, vector/hybrid 1.0. [평가](docs/evaluation.md), [CSV](evaluation/results/) |
| 2026-11-13 / ccdcd0e M11 | macOS arm64·Python 3.12.13, API 136건+scanner 1건 | 모두 통과, integration 5건 제외. 중첩 로그/본문 상한 RED→GREEN, 설정 수용 3건. [보안 증거](docs/security.md) |
| 2026-11-13 / ff0f3ec M12 구현 소스 | macOS fresh clone·Python 3.12.13·Node 22.23.5, API 137/웹 16건 | 모두 통과, lint/typecheck/build·Compose config 통과. [재현 기록](docs/reproducibility.md)·[로그](docs/logs/m12_fresh_local.txt). 원격 CI/Linux Compose는 미실행 |

페이지 번호는 PDF **물리 페이지**(1부터)이며 슬라이드 인쇄 번호와 다를 수 있다. fake 답변은 실제 생성 모델 품질의 증거가 아니다.

## 재현과 CI

저장소 루트에서 비밀 스캔 훅을 켤 수 있다.

```bash
git config core.hooksPath .githooks
python3 scripts/check_secrets.py
python3 scripts/check_secrets.py --history
docker compose --env-file .env.example config --quiet
```

기본 CI는 ruff·format·mypy·pytest·웹 lint/typecheck/test/build·비밀 스캔·Compose config를 검사한다. Actions `workflow_dispatch`에서 integration=true를 선택하면 Linux runner의 새 볼륨에 네 서비스를 띄우고 실제 엔진 5건·브라우저 1시나리오를 실행한다. 로그·스크린샷은 `linux-compose-<commit>` artifact다. 유료 API 키는 필요하지 않다. workflow 파일 작성과 원격 실행 성공은 별도 상태다.

Docker 환경에서 ready 및 브라우저 수용 검증:

```bash
python3 scripts/wait_ready.py
# 루트에서 연 새 터미널; 빈 테스트 컬렉션을 사용한다.
cd apps/web
npm ci
E2E_BASE=http://127.0.0.1:3000 node e2e/browser_flow.mjs ../../data/samples/os_week3_process.pdf ../../.repro/artifacts/screenshots
```

설치된 Chrome이 필요하다. 중복 파일 409를 피하려면 폐기 가능한 새 데이터 환경을 사용한다. 실제 엔진 테스트는 개발용 loopback override를 켠 환경에서 실행한다(기본 Compose의 엔진 포트는 비공개).

```bash
# 저장소 루트
docker compose -f compose.yaml -f compose.override.example.yaml up --build -d --wait
cd apps/api
uv run pytest -m integration
# 유료 키가 없으면 각 항목 SKIP. 있는 키는 비용이 발생하므로 수동 실행한다.
uv run python -m scripts.live_smoke --embedding --openai --claude
```

[아키텍처](docs/architecture.md), [고객 요구](docs/requirements.md), [인수인계](docs/handoff.md), [ADR 001~008](docs/decisions/)에서 구조·선택 이유·다음 한 작업을 확인할 수 있다.

# 강의자료 RAG 검색

한국어 강의 PDF에서 질문의 근거를 찾고 원문 페이지로 확인하는 검색 서비스다. 반복 학습 중 개념과 출처를 다시 확인하는 흐름에 집중한다. FastAPI·React/TypeScript·Qdrant·OpenSearch의 BM25/vector/RRF hybrid를 비교할 수 있다.

## 현재 상태

M1~M7 구현, M8 삭제·재시도·격리 회귀 구현, 로컬 실제 엔진 integration 5개 통과. Docker 컨테이너 기동은 아직 미검증이다. 정확한 결과와 남은 항목은 [진행보고](docs/구현_진행보고.md), [작업목록](docs/구현_작업목록.md), [handoff](docs/handoff.md) 참조.

## 실행

Docker Compose v2, Docker Desktop에 충분한 메모리(로컬 임베딩 모델 포함)와 디스크가 필요하다. 첫 실행은 모델 다운로드에 시간이 걸린다.

```bash
cp .env.example .env
# .env의 AUTH_SECRET을 32바이트 이상 난수로 교체한다.
# 기관·계정 파일이 없으면 SEED_ON_START=true일 때 example 파일을 읽는다.
docker compose up --build -d
docker compose ps
curl http://localhost:8000/api/v1/health/ready
```

웹: http://localhost:3000. API: http://localhost:8000/docs. 키 없이 `EMBEDDING_PROVIDER=local`, `EMBEDDING_MODEL=BAAI/bge-m3`, `ANSWER_PROVIDER=fake`가 기본이다. fake는 동작 검증용이며 생성 모델의 답변 품질을 보여주지 않는다.

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

Python 3.12, uv, Node.js가 필요하다. Docker 없는 macOS 검증 방법은 [로컬 엔진 안내](infra/local/README.md).

```bash
cd apps/api
uv sync --locked
uv run pytest
uv run ruff check .
uv run mypy app
# 별도 터미널
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
- `evaluation/`: 평가 도구 예정. 수업 자료는 `evaluation/private/`에만 둔다.

혼자 운영할 수 있도록 SQLite·파일 볼륨·단일 프로세스 큐를 사용한다. 삭제는 원장을 먼저 `deleting`으로 바꿔 접근을 차단한 후 인덱스→파일→청크를 정리한다. 중간 실패는 비공개 상태로 유지하고 관리자가 재시도한다.

## 한계

- 텍스트 PDF만 지원. 스캔·표·다단 레이아웃은 품질 저하 또는 실패.
- 단일 프로세스·단일 워커. 동시 업로드는 직렬 처리.
- 로컬 임베딩은 CPU라 색인이 느리다. 측정 조건은 docs/performance.md 참조.
- 평가 표본이 작아 일반적 우월성을 주장하지 않는다. M9 정식 평가는 미실행.
- 데모 인증은 정적 계정·HS256 JWT. 공개 배포에는 별도 인증·TLS 필요.
- OpenSearch 보안 플러그인을 끄고 내부 네트워크에만 둔다. 외부 공개 금지.
- 외부 LLM을 선택하면 질문과 검색 근거가 해당 제공자에 전송된다. 개인정보·내부 문서를 반입하지 않는다.
- reranker·Ollama·OCR·Spring gateway는 미구현.

## 다음 작업

Docker 환경에서 fresh 기동·전체 흐름 검증 후 M8 완료와 `v0.1` 태그를 확정한다. 이후 M9 평가→M10 성능→M11 보안→M12 재현성·CI 순으로 진행한다. 데이터 삭제를 수반하는 `docker compose down -v`는 검증용 환경에서만 실행한다.

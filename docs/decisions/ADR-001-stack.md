# ADR-001 스택·이미지 태그·패키지 버전 고정

- 상태: 채택
- 날짜: 2026-11-12
- 관련: 설계서 3.1, 3.3, 9.1

## 결정

### Docker 이미지 (Docker Hub / ghcr API로 2026-11-12에 확인, 모두 linux/arm64 포함)

| 용도 | 태그 | digest (manifest list) | 태그 갱신일 |
|---|---|---|---|
| qdrant | `qdrant/qdrant:v1.20.0` | `sha256:9bfc89f9914fc14876a88c05270685921a55b8877b254a98bcc1cc2f0a424cd2` | 2026-10-21 |
| opensearch 기반 | `opensearchproject/opensearch:2.19.7` | `sha256:3bfa1ec74d56928c2e018033d45c460ce2c0ea65a5cedd577de3102326c31b89` | 2026-10-26 |
| api 기반 | `python:3.12.16-slim-bookworm` | `sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df` | 2026-11-05 |
| uv 바이너리 | `ghcr.io/astral-sh/uv:0.11.6` | (태그 존재만 확인, HTTP 200) | - |
| web 빌드 | `node:22.23.5-alpine` | `sha256:1314fb30ec37592d5845e5a160d522c0e680972aa534549940b8d73bde88481a` | 2026-11-12 |
| web 서빙 | `nginx:1.30.6-alpine` (stable) | `sha256:583b7f2fce1cdb8da5ad5c39ebd3c33b98b87d493190e548bdee1fa8c619c311` | 2026-11-06 |

- qdrant는 설계서 예시의 "v1.1x 계열" 대신 v1.20.0을 고른다. 설치된 `qdrant-client` 1.20.0과 minor 버전을 맞추기 위해서다(클라이언트는 서버와 minor 1 이내 차이를 권장).
- OpenSearch는 설계서대로 2.19 계열 최신 패치(2.19.7). 3.x는 쓰지 않는다.

### Python 패키지 (`apps/api/uv.lock`, Python 3.12.13 로컬 / 3.12.16 이미지)

fastapi 0.162.5, uvicorn 0.54.0, pydantic 2.14.3, pydantic-settings 2.16.2, sqlalchemy 2.1.8, opensearch-py 3.2.0, qdrant-client 1.20.0, pymupdf 2.1, tiktoken 0.14.0, sentence-transformers 6.3.0, transformers 5.22.2, torch 2.15.0 (linux는 2.15.0+cpu), openai 3.49.0, anthropic 2.8.0, pyjwt 2.15.1, bcrypt 5.0.0, cachetools 8.0.0, httpx 0.28.1, numpy 2.5.4, python-multipart 0.0.33, pyyaml 6.0.3. dev: pytest 9.2.0, ruff 0.17.4, mypy 2.4.1.

### 프런트엔드 (`apps/web/package-lock.json`)

react 18.3.1 / react-dom 18.3.1 (설계서 14장의 React 18), react-pdf 10.5.0, react-router-dom 7.18.5, @tanstack/react-query 5.107.1, vite 8.3.8, @vitejs/plugin-react 6.3.0, typescript 5.9.3, vitest 5.1.0, eslint 10.14.0, typescript-eslint 8.72.2.

- react-pdf 11.x와 react-router 8.x는 React 19를 요구하므로 설계서의 React 18을 지키기 위해 한 단계 낮은 major를 고정했다.
- typescript 7.x는 typescript-eslint의 peer 범위(<6.1) 밖이라 5.9.3으로 고정했다.

## 설계서와 달라진 점 (설계서 해당 절도 함께 수정)

1. **torch 휠 출처** (설계서 3.3): "linux/aarch64용 CPU 휠이 PyPI에 있다"는 전제가 현재 사실이 아니다. PyPI의 torch 2.15.0 linux aarch64 휠은 `nvidia-*-cu13`, `triton` 의존성을 끌어온다(`uv lock` 결과에서 확인). 따라서 `pyproject.toml`의 `[tool.uv.sources]`로 **linux 전체**에서 `https://download.pytorch.org/whl/cpu` 인덱스의 `2.15.0+cpu` 휠을 쓰도록 고정했다. macOS 개발 환경은 PyPI 휠을 쓴다. lock 후 `nvidia` 패키지 0개 확인.
2. **HF 캐시 경로** (설계서 3.1): api 컨테이너는 비루트(`app`, uid 10001)로 실행하므로 `/root/.cache/huggingface`에 쓸 수 없다. `HF_HOME=/home/app/.cache/huggingface`로 두고 `hf_cache` 볼륨을 그 경로에 붙인다.
3. **호스트 포트 바인딩**: api(8000), web(3000)도 `127.0.0.1`에만 바인딩한다. 데모가 로컬 전용이고 OpenSearch 보안 플러그인을 끈 구성과 일관되게 하기 위해서다. 외부 공개가 필요하면 README의 공개 배포 절을 따른다.
4. **web 비루트 실행**: `nginx:alpine`을 그대로 쓰되 `USER nginx`, `listen 8080`, pid·임시 파일을 `/tmp`로 옮겼다. 호스트 3000 → 컨테이너 8080.
5. **qdrant healthcheck**: 이미지에 curl이 있는지 확인하지 못했으므로(로컬에 Docker 없음) bash `/dev/tcp`로 `/readyz`를 호출한다. Docker 환경에서 첫 기동 시 확인 필요.
6. **추가 환경변수**: `APP_COMMIT`(빌드 인자로 주입, `/meta`에 노출), `RATE_LIMIT_QUERY_PER_MINUTE`, `RATE_LIMIT_ANSWERS_PER_MINUTE`, `RATE_LIMIT_UPLOAD_PER_HOUR`(설계서 8.4 "환경변수로 조정 가능"의 구체 이름). `.env.example`과 `core/config.py`에 함께 추가했다.

## 검증 상태

- `uv lock`, `uv sync`, `npm install`, `npm run build`, `docker compose config`(standalone compose v5.7.1 바이너리) 통과.
- 이 작업 환경에는 Docker 데몬이 없어 이미지 빌드·기동은 아직 확인하지 못했다. 첫 Docker 환경에서 `docs/performance.md`의 M1 절을 채운다.

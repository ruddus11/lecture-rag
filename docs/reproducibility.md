# M12 재현 검증 기록

## 범위와 기준

2026-11-13, feat/m11-m12, 기준 062ede3 + M11 ccdcd0e. macOS arm64, uv 0.11.6, Python 3.12.13.
원격 push 금지로 Actions 실행은 하지 않는다. Docker executable/daemon 부재로 Linux 컨테이너 기동·이미지 build·fresh 볼륨 E2E는 미실행이다. main의 M8 검증 결과와 합쳐 판단해야 한다.

## 로컬 결과

- API: `uv sync --locked`, `uv run pytest` → **137 passed, 5 integration deselected** (22.80초).
- `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy app` 통과(60 source files).
- 웹: `npm ci`, lint·typecheck·test **16 passed**, build 통과. 기본 Node 25.8.0에서는 engine warning이 있으므로 fresh 재현은 CI와 같은 Node 22.23.5를 사용한다.
- `docker-compose --env-file .env.example config --quiet` → standalone Compose 통과. Docker 기동과 구분한다.
- workflow YAML 파싱·checks/integration job·contents:read 권한 구조 확인. Actions 실행 검증을 대체하지 않는다.
- `prepare_env.py`: 새 .env 난수 길이 ≥32바이트·0600, 기존 파일 재실행 거부·내용 유지 확인. 최초 Path.open(opener) 오류를 발견하여 built-in open으로 수정하고 재확인했다.
- 유료 smoke: OpenAI embedding·OpenAI answer·Claude answer 모두 **SKIP** (키 없음).

## Fresh clone

M12 구현 커밋을 저장소 내부 `.repro/checkout`에 `git clone --no-hardlinks`하여, 기존 가상환경/node_modules 없이 lock install부터 재검증한다. 최종 실행 결과는 아래 로그에 첨부했다. 기존 실제 실행 데이터와 private 자료는 복사하지 않는다.

## Linux 실행 절차와 남은 게이트

원격 업로드를 승인한 별도 작업에서 `.github/workflows/ci.yml`의 workflow_dispatch integration=true를 실행한다. 네 서비스 compose→ready→실제 엔진 5건→브라우저 1건 결과와 `linux-compose-<commit>` artifact 링크를 이 문서에 붙인다. integration 실패 시 compose 로그·ps·메모리 artifact로 원인을 확인한다. 이 성공 로그와 README 모든 명령의 Docker 환경 재실행 전까지 **M12 전체 완료는 보류**한다.

README의 Docker 시작·ready·실제 엔진·Chrome 명령은 이 머신에서 실행하지 못했다. `infra/local` 네이티브 실행은 Docker 수용 증거로 바꾸지 않는다. v0.1 태그는 main 담당자가 결정한다.


## Fresh clone 최종 결과

- 2026-11-13 03:42 UTC, 소스 `ff0f3ecd656f1ca55da2a0f1ac34d9817179f905` (M12 구현 커밋; 이후 변경은 결과 문서·로그만).
- `git clone --no-hardlinks . .repro/checkout` 후 새 `.venv`, 새 node_modules를 생성했다. 엔진·실행 데이터·기존 .env는 복사하지 않았다.
- Node **22.23.5**, Python **3.12.13**, uv **0.11.6**, Darwin arm64.
- lock 설치, API **137 passed / 5 deselected (27.14초)**, ruff·format·mypy 및 루트 scripts 검사 통과.
- npm ci·lint·typecheck, 웹 **16 passed**, build 통과. Node engine 경고 **0건**.
- .env 초기화·훅 설정·index **204 blobs / 0 findings**, 이력 **288 blobs / 0 findings**, standalone Compose config 통과.
- 유료 smoke 3항목 모두 키 없음 SKIP. API 디렉터리에서 실행한 smoke의 AUTH_SECRET 경고는 루트 .env를 자동 로드하지 않기 때문이며 키 설정·외부 호출은 하지 않았다.
- 개인 개발 환경 경로가 포함된 원본 실행 로그는 공개 대상에서 제외한다. 위 결과는 기존 검증 기록의 요약이며 이번 공개 자료 정리에서 테스트를 재실행한 결과는 아니다.

이 결과는 macOS fresh clone의 **로컬 명령** 재현 증거다. README의 Docker·Chrome 실기동 명령을 모두 성공했다는 뜻은 아니므로 작업목록의 전체 재현 게이트는 미체크 상태다.

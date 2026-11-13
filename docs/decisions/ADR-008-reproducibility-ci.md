# ADR-008 재현성, CI와 검증 증거

- 상태: 채택 (Linux 실행 게이트 미검증)
- 날짜: 2026-11-13

## 결정

uv.lock과 package-lock.json을 유지하고 Python 3.12·Node 22.23.5를 CI에서 고정한다. 항상 실행하는 checks job은 비밀 스캔·ruff·format·mypy·unit/API pytest·웹 lint/typecheck/test/build·compose config를 수행한다. 유료 API를 CI에 연결하지 않는다.

workflow_dispatch integration job은 Linux x86_64에서 새 볼륨으로 네 서비스를 빌드·기동하고, ready 확인→실제 엔진 integration→브라우저 1시나리오를 실행한다. 생성 모델은 fake, 임베딩은 기본 bge-m3다. 테스트용 .env는 난수 AUTH_SECRET으로 생성하고 artifact에 넣지 않는다. 결과·로그·스크린샷은 14일 artifact로 남긴다. 볼륨 삭제는 폐기 가능한 Actions runner에서만 한다.

로컬 fresh checkout 검증은 기존 checkout의 캐시·실행 데이터 없이 lock install부터 반복한다. macOS 성공을 Linux compose 성공으로 해석하지 않는다. push 금지 요청에 따라 이 세션에서 workflow를 원격 실행하거나 녹색 상태를 주장하지 않는다. ADR-001~007은 기존 결정을 유지하고 ADR-010의 외부 게이트 보류 규칙을 따른다.

## Trade-off

항상 실제 엔진·모델을 내려받으면 CI 비용과 시간이 커진다. 기본 fake 단위/API 검증으로 빠른 루프를 유지하고, 무거운 Linux 수용 검증을 수동 job으로 분리한다. 이 job의 최초 성공 전 M12 전체 완료는 보류한다.

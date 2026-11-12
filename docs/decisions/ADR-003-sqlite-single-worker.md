# ADR-003 SQLite 원장 + 파일 볼륨, 단일 워커

- 상태: 채택
- 날짜: 2026-11-12
- 관련: 설계서 4.1, 5.1, 18장

## 맥락

데모·포트폴리오 규모(기관 2개, 문서 수십 개, 동시 사용자 소수)에서 별도 DB 서버와 메시지 브로커는 운영 부담만 늘린다. 다만 업로드 처리 상태, 권한 판단, 인용 검증의 원천이 되는 "원장"은 하나여야 한다.

## 결정

- 원장은 SQLite 한 파일(`/data/app.db`, `api_data` 볼륨). SQLAlchemy 2.x 동기 세션, 연결마다 `PRAGMA journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout=30000`.
- 마이그레이션 도구 없이 `create_all` + `schema_version`(현재 1). 버전이 다르면 `storage/db.py::migrate`에서 수동 처리하고, 지원하지 않는 버전이면 기동을 실패시킨다.
- 작업 큐도 SQLite(`ingestion_jobs`)이며, API 프로세스 안의 asyncio 태스크 1개가 1초 간격으로 폴링한다. uvicorn `--workers 1` 고정.
- 문서 원본은 `/data/files/{document_id}.pdf`. 원본 파일명은 DB에만 둔다.
- yaml(`config/*.yaml`)은 정책 선언이고, 권한 판단은 항상 SQLite의 `users`·`collections`로 한다. 기동 시 `SEED_ON_START=true`면 upsert하며, 기존 컬렉션의 `version`은 유지한다. 실제 yaml이 없으면 같은 폴더의 `*.example.yaml`로 시드한다(fresh clone 기동용).
- yaml의 `answer`·`upload` 블록은 현재 선언으로만 둔다. 답변 provider는 `.env`의 `ANSWER_PROVIDER`가, 업로드 한도는 서버 고정값(20MB·200쪽, 설계서 8.3)이 정한다. 기관별로 다르게 할 필요가 생기면 `institutions` 테이블에 컬럼을 추가한다.

## 결과

- 장점: 의존성 0개, 백업은 볼륨 복사, 트랜잭션으로 활성화·삭제의 원자성 확보.
- 한계: 쓰기 동시성이 낮고 프로세스가 하나라 수평 확장 불가. 동시 업로드는 직렬 처리된다(README 한계 절). async 라우트 안에서 동기 SQLite 호출을 하므로 긴 쿼리가 생기면 이벤트 루프가 막힌다. 현재 쿼리는 모두 인덱스 조회 수준이다.
- 확장 경로: Postgres + 별도 워커 프로세스. 모델은 SQLAlchemy이므로 엔진 URL과 부분 유니크 인덱스(`postgresql_where`)만 바꾸면 된다.

## 부록 (2026-11-12, M4): 데모 계정 `b_admin` 추가

설계서 4.4의 데모 사용자는 `a_admin`·`a_student`·`b_student` 셋이라 campus_b에는 업로드할 수 있는 계정이 없다. campus_b `networks` 컬렉션에 자작 샘플을 올리고 기관 A/B 격리(문서·작업·파일·검색·인용)를 양방향으로 확인하기 위해 `b_admin`(campus_b, admin)을 `config/users*.yaml`에 추가했다. 비밀번호는 README에만 적는다. 설계서 4.4에도 반영했다.

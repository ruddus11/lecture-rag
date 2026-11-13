# ADR-011 질문 임베딩 기회적 묶음 처리 (QueryBatcher)

- 상태: 채택
- 날짜: 2026-11-13
- 관련: 설계서 10.2-2, `apps/api/app/retrieval/embeddings/batcher.py`, `app/container.py`, `app/retrieval/service.py`, ADR-006

## 배경

M10 baseline(커밋 `062ede3`, 캐시 미연결)에서 hybrid 검색 서버 `timings_ms`를 보면 `embed_query`가 전체의 90% 이상이다
(동시 1: p50 41.5ms / total 44.5ms). 동시 5에서는 `embed_query` p50이 125ms로 세 배가 된다. 요청마다 `asyncio.to_thread`로
따로 `encode`를 부르면 torch CPU 스레드(4개)를 여러 호출이 나눠 쓰면서 서로 느려지기 때문이다.
같은 머신에서 bge-m3로 잰 값: 1건 39ms, 5건 batch 1회 57ms, 5개 스레드 동시 1건씩 124ms(round당).

## 결정

- `QueryBatcher`를 둔다. 인코더가 놀고 있으면 즉시 1건을 보내고, 인코딩 중에 들어온 질문은 쌓아 두었다가 끝나는 즉시
  최대 16건을 한 번에 보낸다. **대기 창(timer)이 없다**. 따라서 동시성 1의 지연은 늘지 않는다.
- batch 안 동일 문장은 한 번만 인코딩한다. 인코딩 오류는 그 batch를 기다리던 모든 요청에 같은 예외로 전달하고(엔진 장애와 같은
  degraded/503 경로), 타임아웃으로 취소된 요청은 결과만 버린다.
- provider에 `embed_queries(texts)`가 있으면 쓰고(로컬 ST), 없으면 한 건씩 부른다(OpenAI·테스트 fake).
- 인코딩은 여전히 이벤트 루프 밖 스레드에서 하며 15초 상한(`EMBED_QUERY_TIMEOUT_SECONDS`)도 그대로다.
- 설정값을 새로 두지 않는다(상수 `MAX_BATCH=16`). 단일 프로세스·단일 워커 가정(ADR-003) 안에서만 의미가 있다.

## 대안

- 고정 대기 창(예: 5ms) 묶음: 동시 1 지연이 늘어 채택하지 않음.
- 전역 lock으로 직렬화: CPU 경합은 없어지지만 동시 5에서 뒤 요청이 앞 4건을 다 기다려 p95가 나빠진다.
- 임베딩 전용 프로세스/서버(TEI 등): 단일 compose 범위를 넘는다. 사용자 증가 시 다음 단계.

## 결과

`docs/performance.md` 표 1(알고리즘/병렬)에 before/after를 적는다. 캐시(ADR-008)와 효과를 섞지 않도록 표 1은 캐시 TTL 0으로 잰다.

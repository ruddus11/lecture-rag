# ADR-002 앱 계층 RRF (엔진 내장 hybrid 미사용)

- 상태: 채택
- 날짜: 2026-11-12
- 관련: 설계서 6.2~6.4, `apps/api/app/retrieval/{fusion,service}.py`

## 맥락

BM25는 OpenSearch, 벡터는 Qdrant에 있다. OpenSearch의 neural/hybrid 쿼리나 Qdrant의 sparse+dense fusion을 쓰려면 한 엔진에 두 표현을 모두 넣어야 하고, 엔진 하나가 죽으면 hybrid 전체가 죽는다. 두 엔진의 점수 척도(BM25 점수와 코사인)는 직접 더할 수 없다.

## 결정

- 두 엔진을 `asyncio.gather`로 병렬 호출하고(각 `SEARCH_ENGINE_TIMEOUT_MS`, 기본 2초, 질문 임베딩은 별도 15초 상한), 결과 순위만으로 앱에서 RRF를 계산한다. `score = Σ 1/(k + rank)`, `k = rrf_rank_constant`(기본 60), rank는 1부터.
- 같은 엔진 결과 안의 중복 chunk는 최상위 rank만 쓴다. 동점은 `(vector rank 있음 우선, chunk_id 사전순)`.
- 단일 모드도 같은 함수를 지난다(한쪽만 있는 RRF = 원래 순서). 그래서 세 모드의 중복 제거·페이지 상한·원장 대조 규칙이 같고, 평가에서 모드 차이가 융합 외 요인으로 생기지 않는다.
- 순서: RRF → 원장 대조(ready·active_version·scope) → 페이지당 상한(`max_chunks_per_page`) → `top_k`(검색) 또는 `context_k`(답변). 설계서 6.3은 페이지 상한을 융합 직후에 두지만, 오래된 버전 청크가 페이지 자리를 먼저 차지해 정상 청크를 밀어내지 않도록 원장 대조 뒤로 옮겼다.
- 부분 장애: hybrid에서 한쪽이 실패·타임아웃이면 다른 쪽으로 응답하고 `degraded=true`, `modes_used`에 실제 사용한 엔진만 적는다. 둘 다 실패하거나 단일 모드의 엔진이 실패하면 503 `search_unavailable`(retryable).
- 검색 프로필은 첫 요청 컬렉션(요청이 비면 slug 순 첫 허용 컬렉션)의 `search_profile`을 쓴다. 시드 기준 기관 내 프로필이 같으므로 차이가 없고, 다르게 둘 경우 이 규칙을 README에 적는다.

## 결과

- 단위 테스트 `tests/unit/test_fusion.py`(점수 합, 동점, 한쪽 부재·중복, 페이지 상한), API 테스트 `tests/api/test_search_hybrid.py`(세 모드, degraded, 503, 타임아웃), integration `tests/integration/test_pipeline_live.py`(실제 엔진, OpenSearch 중단 시 degraded).
- 엔진 점수 정보는 버린다. score threshold 같은 기능이 필요해지면 엔진별 정규화가 따로 필요하다.

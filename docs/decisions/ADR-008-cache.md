# ADR-008 캐시 키 구성과 무효화

- 상태: 채택
- 날짜: 2026-11-13
- 관련: 설계서 9.2-7, 10.1, 10.2-6, `apps/api/app/core/cache.py`, `app/retrieval/service.py`, `tests/api/test_cache.py`

## 결정

단일 프로세스 `cachetools.TTLCache` 두 개를 쓴다. 단일 워커 가정(ADR-003)이라 프로세스 간 공유·일관성 문제가 없다.

| 캐시 | 키 | 값 | TTL / 크기 | 환경변수 |
|---|---|---|---|---|
| 질문 임베딩 | `sha256(embedding_model \x00 normalize_query(q))` | 벡터 | 3600s / 2000 | `CACHE_EMBED_TTL_SECONDS` |
| 검색 결과 | `sha256(json[normalize_query(q), mode, candidate_k, limit(top_k 또는 context_k), rrf_k, max_chunks_per_page, index_profile_id, keyword_analyzer, scope_fingerprint])` | `(modes_used, 융합·원장 대조·페이지 상한까지 끝난 후보 목록)` | 300s / 1000 | `CACHE_RETRIEVAL_TTL_SECONDS` |

- `scope_fingerprint` = 허용 컬렉션 `id:version` 정렬 목록의 sha256(`core/scope.py`). 컬렉션 id는 기관에 속하므로 기관·역할이
  다르면 허용 집합이 달라 키가 달라진다. 같은 기관·같은 허용 집합의 사용자끼리는 결과를 공유한다(볼 수 있는 자료가 같기 때문).
- 문서 활성화·삭제 요청·삭제 완료 시 `collection.version`이 오르므로 이전 키는 자연히 쓰이지 않는다. 추가로 `invalidate_caches()`가
  두 캐시를 모두 `clear()` 한다(활성화, 삭제 요청, 삭제 워커 완료, 재시도 시점).
- **적중 결과도 원장 대조(`ledger_check`)를 다시 한다.** 키 버그나 clear 누락이 있어도 scope 밖·ready 아님·이전 버전 청크는 응답에 나오지 않는다.
- `degraded=true` 결과(한쪽 엔진 장애)는 저장하지 않는다. 엔진 복구 뒤 TTL 동안 반쪽 결과가 남는 것을 막는다.
- 응답 `cache_status`: `off`(두 캐시 TTL 0) | `miss` | `embed_hit`(임베딩만 적중) | `hit`(검색 결과 적중). `query_logs.cache_status`에도 남는다.
- 정확도 평가(M9 `run_retrieval`)는 API를 `CACHE_*_TTL_SECONDS=0`으로 띄워 실행한다. 지연 측정은 표마다 캐시 상태를 적는다.
- 답변 캐시(`CACHE_ANSWER_ENABLED`)는 구현하지 않고 기본 off를 유지한다. 현재 답변 provider가 fake라 효과를 잴 수 없고,
  실제 LLM 응답을 공유하려면 생성 후 삭제·권한 변경 재검사(`AnswerService.done`)를 캐시 적중 경로에도 같은 방식으로 붙이는 테스트가
  먼저 필요하다. 유료 키로 답변 지연을 잰 뒤 다시 판단한다.

## 메모리 상한(추정)

임베딩 1024차원 float 리스트 1건 ≈ 32KB → 2000건 ≈ 64MB. 검색 결과 1건은 후보 최대 10개(청크 본문 포함) ≈ 수십 KB → 1000건 ≈ 수십 MB.
api `mem_limit: 4g`(설계서 3.2) 대비 여유가 있다. 실측 RSS 변화는 `docs/performance.md`에 적되, torch 할당자 변동과 분리해 읽는다.

## 검증 (`tests/api/test_cache.py`)

- 같은 질문(공백만 다름) 두 번째 요청 `hit`, 임베딩 재호출 없음. 모드가 다르면 `embed_hit`.
- TTL 0이면 `off`이고 캐시에 아무것도 쌓이지 않음.
- admin이 채운 `ta_only` 결과가 같은 기관 student·타 기관 student에게 `hit`로 나오지 않고 0건.
- 키를 강제로 같게 만들어도(가상의 버그) 적중 결과의 원장 대조로 타 사용자에게 0건.
- 삭제 직후 TTL 안 재검색에 삭제 문서 없음. clear와 버전 키를 모두 무력화해도 `hit` 결과에 삭제 문서 없음.
- 활성화로 버전이 오르면 clear 없이도 이전 키 미사용. degraded 결과 미저장, 복구 후 정상 결과.

## 대안

- Redis 등 외부 캐시: 단일 워커 범위에서 필요 없음. 다중 워커로 갈 때 키 규칙은 그대로 옮긴다.
- 사용자 id를 키에 넣기: 같은 권한의 사용자끼리 공유를 막아 적중률만 낮추고 안전성은 scope_fingerprint·원장 대조와 같다.

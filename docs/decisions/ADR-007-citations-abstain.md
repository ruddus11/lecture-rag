# ADR-007 인용 검증 규칙과 보류 정책, Claude fallback 미사용

- 상태: 채택
- 날짜: 2026-11-12
- 관련: 설계서 7장, `apps/api/app/generation/*`

## 결정

1. 근거는 같은 요청에서 검색한 상위 `context_k`개 청크만 쓴다. LLM에는 `c1..cN` 로컬 ID만 보이고, 응답의 `citations`는 이 ID를 원장 `chunk_id`로 되돌린 것이다. 그래서 모든 인용은 응답 `hits` 안에 있다.
2. 검증 순서(설계서 7.3 그대로): 거부 → `provider_refused`, 초안 없음 → `provider_error`, `insufficient_evidence` → 같은 이름, 빈 답 → `empty_answer`, 인용 없음 → `no_citations`, ID 불일치·quote 불일치 인용은 버리고 모두 버려지면 `invalid_citations`. quote는 공백을 1칸으로 정규화한 뒤 부분 문자열이면 통과, 아니면 같은 길이 슬라이딩 윈도우 `SequenceMatcher.ratio() ≥ 0.9`.
3. `invalid_citations`만 같은 근거로 1회 재생성한다(`ANSWER_MAX_ATTEMPTS=2`). 다른 보류 사유는 재시도하지 않는다. usage는 시도 합계.
4. 검색 0건이면 LLM을 부르지 않고 `no_evidence`.
5. 공급자 오류 매핑(Claude·OpenAI 공통): RateLimit → HTTP 429 `provider_rate_limited`(`Retry-After: 30`), 연결 오류·타임아웃·5xx → **HTTP 200 + `abstained=true, abstain_reason="provider_unavailable", degraded=true`, hits만 제공**, 그 밖의 4xx → HTTP 500 `provider_error`(메시지는 로그에만). 설계서 7.1의 "503 매핑"과 7.3의 "503 계열 실패는 degraded 보류로 hits 제공"이 겹치므로 7.3을 따랐다. 답변 생성 상한은 `ANSWER_TIMEOUT_SECONDS`(30초)이고 넘으면 503 계열로 본다.
6. Claude: `messages.parse(model, max_tokens=2048, system, messages, output_format=AnswerDraft, output_config={"effort":"low"})`. `thinking`은 보내지 않고 서버측 `fallbacks`도 쓰지 않는다. 거부(`stop_reason="refusal"`)는 다른 모델로 우회하지 않고 보류로 처리하는 것이 서비스 정책이다. SDK 재시도는 1회.
7. OpenAI: Responses API `responses.parse(model, instructions, input, text_format=AnswerDraft, max_output_tokens=2048)`, 응답 output에 `refusal` 항목이 있으면 거부. 모델 ID(`OPENAI_CHAT_MODEL`)는 키가 없어 `GET /v1/models`로 확인하지 못했으므로 `.env.example`은 빈 값으로 두고, 비어 있으면 기동을 거부한다.
8. prompt injection 방어: 근거를 데이터로 선언(system 4번), 근거·제목·질문을 HTML 이스케이프해 `</evidence>` 흉내로 경계를 깨지 못하게 함, 인용 ID를 로컬 ID 집합으로 제한, 검증기가 집합 밖 인용을 버림.

## 검증

- 단위: `tests/unit/test_citations.py`(사유별 보류, 부분 폐기, 유사도 윈도우, prompt 이스케이프), `tests/unit/test_llm_providers.py`(SDK 호출 인자·usage·거부·오류 매핑, 네트워크 없음).
- API(fake): `tests/api/test_answers.py` 정상 인용 ⊂ hits, 무효 ID·quote 불일치 → 1회 재시도 후 보류, 0건 시 LLM 미호출, `[[no_evidence]]`, 공급자 503→degraded 보류, 429/500 매핑, injection PDF.
- 실제 OpenAI·Claude 호출은 키가 없어 실행하지 못했다(`scripts/live_smoke.py` SKIP). 형식 검증 통과는 의미적 정확성의 증거가 아니다.

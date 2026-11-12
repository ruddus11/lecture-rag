# 평가

(M9에서 지표 정의·결과 표·실패 사례를 채운다.)

## 부록 A. live smoke (실제 provider 1회 호출)

| 날짜 | 항목 | 결과 | 모델 ID | usage | 비고 |
|---|---|---|---|---|---|
| 2026-11-12 | OpenAI 임베딩 | SKIP | - | - | `OPENAI_API_KEY` 없음 |
| 2026-11-12 | OpenAI 답변 | SKIP | - | - | `OPENAI_API_KEY`·`OPENAI_CHAT_MODEL` 없음 |
| 2026-11-12 | Claude 답변 | SKIP | - | - | `ANTHROPIC_API_KEY` 없음 |

실행: `cd apps/api && uv run python -m scripts.live_smoke --embedding --openai --claude` (루트 `.env`의 키를 쓴다). 출력 JSON(응답 초안·usage·모델 ID)을 이 표에 옮긴다. 키는 출력되지 않는다.

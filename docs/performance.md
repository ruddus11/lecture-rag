# 성능 기록

모든 수치는 실측값만 적는다. 측정하지 못한 항목은 "미측정"과 이유를 적는다.

## M1 유휴 메모리 (`docker stats`)

| 날짜 | commit | 환경 | qdrant | opensearch | api | web | 합계 |
|---|---|---|---|---|---|---|---|
| 2026-11-12 | M1 | 구현 머신(macOS arm64, 24GB) | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 |

미측정 이유: 구현 머신에 Docker(데몬·CLI)가 설치되어 있지 않다. `docker compose config`만 standalone compose 바이너리로 검증했다. Docker Desktop 환경에서 `make up` 후 `docker stats --no-stream`으로 채운다.

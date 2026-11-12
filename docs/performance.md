# 성능 기록

모든 수치는 실측값만 적는다. 측정하지 못한 항목은 "미측정"과 이유를 적는다.

## M1 유휴 메모리 (`docker stats`)

| 날짜 | commit | 환경 | qdrant | opensearch | api | web | 합계 |
|---|---|---|---|---|---|---|---|
| 2026-11-12 | M1 | 구현 머신(macOS arm64, 24GB) | 미측정 | 미측정 | 미측정 | 미측정 | 미측정 |

미측정 이유: 구현 머신에 Docker(데몬·CLI)가 설치되어 있지 않다. `docker compose config`만 standalone compose 바이너리로 검증했다. Docker Desktop 환경에서 `make up` 후 `docker stats --no-stream`으로 채운다.

## M4 로컬 임베딩 처리량·메모리 (호스트 실측, 컨테이너 아님)

측정: 2026-11-12, commit `8b86a31`+M4 작업트리, Apple M5(10코어)·24GB, macOS arm64, Python 3.12.13, torch CPU(`device="cpu"`), sentence-transformers 6.3.0. 입력은 자작 샘플 3종을 3번 반복한 81쪽 PDF → 81청크(평균 183 cl100k 토큰). 명령: `python -m scripts.bench_embed <model> /tmp/lrag_e2e/big_restart.pdf` (warm-up 4청크 후 측정, 질문 임베딩은 20회 평균).

| 모델 | dim | 모델 적재(s) | 81청크 임베딩(s) | 청크/초 | 질문 1건(ms) | 프로세스 최대 RSS(MB) |
|---|---|---|---|---|---|---|
| BAAI/bge-m3 | 1024 | 6.5 | 9.01 | 9.0 | 93.6 | 2512 |
| intfloat/multilingual-e5-small | 384 | 6.4 | 1.14 | 71.1 | 10.6 | 1183 |

- API 프로세스(uvicorn, bge-m3 적재 + 샘플 27청크 색인 후) RSS: 2150MB. 설계서 3.2의 api `mem_limit: 4g` 안이다.
- 실제 수집 작업 로그(`job_finished.stage_ms`, bge-m3, 실제 Qdrant 1.20.0 바이너리): 9~10청크 문서의 embedding 단계 1.2~1.3초, indexing_vector 9~13ms. 첫 문서는 모델 첫 호출 지연으로 5.6초.
- 컨테이너(linux/arm64, CPU 전용 torch 휠)의 수치는 Docker 환경에서 다시 측정해야 한다. 호스트 수치는 상한 참고치로만 쓴다.

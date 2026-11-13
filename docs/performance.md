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

## M10 지연 계측과 개선 (2026-11-13)

### 측정 조건

- 환경: Apple M5(10코어)·24GB, macOS arm64, Python 3.12.13, **컨테이너 아님**(Docker 없음). Qdrant 1.20.0·OpenSearch 2.19.7+Nori 네이티브
  바이너리(`infra/local/engines.sh`, 포트 6433/9210), API는 uvicorn 단일 워커(`infra/local/api.sh 8020`), 임베딩 bge-m3 CPU, 답변 provider `fake`.
- 데이터: `data/samples` 자작 PDF 3개 색인, 측정 계정 `a_student`가 보는 문서 2개·19청크. 질문은 `evaluation/dataset.dev.jsonl` 30문항을
  순서대로 반복(같은 질문이 n=200 동안 6~7회 반복). rate limit off.
- 명령(라벨만 다름):

  ```bash
  EVAL_USERNAME=a_student EVAL_PASSWORD=... EVAL_CACHE=off \
  apps/api/.venv/bin/python -m evaluation.run_latency --base http://127.0.0.1:8020/api/v1 \
    --endpoint search --mode hybrid --warmup 10 --n 200 --concurrency 1 --label before --api-pid $API_PID
  # answers: --endpoint answers --warmup 3 --n 40, 동시성 5: --concurrency 5
  ```

- 지연은 클라이언트 wall(ms, HTTP 왕복). 서버 `timings_ms`는 별도 열. 오류율은 HTTP 오류 + `degraded=true`를 포함한 전체 표본 기준.
- 메모리는 측정 중 0.5초 간격으로 샘플링한 API 프로세스 RSS 최대값(`ps`). 컨테이너 `docker stats`는 미측정.
- 원자료: `evaluation/results/latency/*.csv`, `*_summary.md`(환경·commit 포함).

### 표 1. 알고리즘/병렬 개선 (캐시 off)

before = `062ede3`(캐시 미연결), after = `7f77d4a`를 `CACHE_EMBED_TTL_SECONDS=0 CACHE_RETRIEVAL_TTL_SECONDS=0`으로 기동. 같은 데이터·같은 엔진 프로세스.
바뀐 것은 동시 질문 임베딩 기회적 batch(ADR-011) 하나다. 10.2의 2~4번 중 나머지는 이미 적용되어 있어 확인만 했다(아래).

| 구분 | commit | endpoint | 동시성 | n | 오류율 | p50 | p95 | 서버 total p50 | 서버 embed_query p50 | 처리량(rps) | RSS 최대(MB) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| before | 062ede3 | search | 1 | 200 | 0% | 46.0 | 51.1 | 44.5 | 41.5 | 21.3 | 1890 |
| after | 7f77d4a | search | 1 | 200 | 0% | 46.4 | 55.6 | 44.7 | 41.7 | 20.8 | 1966 |
| before | 062ede3 | search | 5 | 200 | 0% | 135.8 | 166.4 | 131.9 | 125.0 | 35.9 | 1898 |
| after | 7f77d4a | search | 5 | 200 | 0% | **117.7** | **126.5** | 114.3 | 106.8 | **42.7** | 1976 |
| before | 062ede3 | answers | 1 | 40 | 0% | 45.5 | 47.4 | 43.5 | - | 21.7 | 1898 |
| after | 7f77d4a | answers | 1 | 40 | 0% | 46.8 | 52.0 | 44.8 | - | 21.0 | 1976 |
| before | 062ede3 | answers | 5 | 40 | 0% | 131.5 | 143.1 | 126.5 | - | 37.2 | 1865 |
| after | 7f77d4a | answers | 5 | 40 | 0% | 119.7 | 138.9 | 115.9 | - | 40.9 | 1976 |

search 동시성 5 반복 측정(같은 조건, 각 n=200): before p50 135.8 / 140.7 / 136.1, p95 166.4 / 195.5 / 152.6, 34~36 rps.
after p50 117.7 / 118.6 / 120.3, p95 126.5 / 140.1 / 131.4, 41~43 rps. 동시성 5에서 p50 약 13%, p95 약 15~35% 감소, 처리량 약 18% 증가.
동시성 1은 대기 창이 없는 설계대로 차이가 측정 잡음 범위다(p95 +4ms는 단일 실행 값).

해석:
- 동시성 1에서 hybrid 지연의 93%가 질문 임베딩(bge-m3 CPU 41ms)이다. keyword(BM25) 2~3ms, Qdrant 2ms, 원장 대조·scope 1ms 미만.
  두 엔진은 이미 `asyncio.gather`로 병렬이라 total ≈ max(keyword, embed+vector)다.
- 동시 5에서 before는 요청마다 따로 `encode`를 불러 torch CPU 스레드(4개)를 나눠 썼다. 단독 측정(`scripts/bench_query_batch.py`; 원본 실행 로그는 비공개): 1건 41ms, batch 5 70ms, 5개 스레드 동시 1건씩 113ms. batch 결과 벡터는 1건씩과 같다
  (코사인 최소 1.0, 최대 절대 차 1.6e-7).
- 개선 폭이 batch 단독 비율보다 작은 이유: 닫힌 루프 클라이언트 5개라 batch가 1건과 4건으로 번갈아 생기고, 요청은 진행 중 batch가
  끝나기를 기다린 뒤 자기 batch를 기다린다. 고정 대기 창으로 맞추면 동시 1 지연이 늘어 채택하지 않았다(ADR-011).
- RSS 차이(약 +80MB)는 batch 인코딩의 torch 할당자 증가로 추정하며 단일 프로세스 수치다. 캐시는 이 표에서 꺼져 있다.

### 표 2. 캐시 효과 (`7f77d4a`, 임베딩 → 검색 결과 순으로 켬)

| 구분 | 캐시 | endpoint | 동시성 | n | 오류율 | p50 | p95 | 서버 total p50 | 처리량(rps) | RSS 최대(MB) | cache_status 분포 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 캐시 off (표 1 after) | off | search | 1 | 200 | 0% | 46.4 | 55.6 | 44.7 | 20.8 | 1966 | off 200 |
| 임베딩만 | embed 3600s | search | 1 | 200 | 0% | 3.7 | 44.8 | 2.4 | 121.1 | 2120 | miss 20, embed_hit 180 |
| 임베딩+검색 | embed 3600s, retrieval 300s | search | 1 | 200 | 0% | 1.2 | 45.4 | 0.2 | 156.9 | 2148 | miss 20, hit 180 |
| 캐시 off (표 1 after) | off | search | 5 | 200 | 0% | 117.7 | 126.5 | 114.3 | 42.7 | 1976 | off 200 |
| 임베딩만 | embed 3600s | search | 5 | 200 | 0% | 13.0 | 15.8 | 9.1 | 374.6 | 2120 | embed_hit 200 |
| 임베딩+검색 | embed 3600s, retrieval 300s | search | 5 | 200 | 0% | 4.1 | 5.8 | 0.2 | 1147.6 | 2148 | hit 200 |
| 캐시 off (표 1 after) | off | answers | 1 | 40 | 0% | 46.8 | 52.0 | 44.8 | 21.0 | 1976 | off 40 |
| 임베딩+검색 | embed 3600s, retrieval 300s | answers | 1 | 40 | 0% | 3.7 | 4.3 | 2.3 | 310.5 | 2148 | embed_hit 27, hit 13 |
| 캐시 off (표 1 after) | off | answers | 5 | 40 | 0% | 119.7 | 138.9 | 115.9 | 40.9 | 1976 | off 40 |
| 임베딩+검색 | embed 3600s, retrieval 300s | answers | 5 | 40 | 0% | 5.5 | 6.5 | 0.3 | 809.4 | 2148 | hit 40 |

- **반복 질문 작업부하라 낙관적인 수치다.** 30개 질문을 200번 돌려 적중률이 90~100%다. 처음 보는 질문(miss 행)은 캐시 off와 같은
  지연(임베딩 p50 41ms)이고, p95가 45ms로 남은 것이 그 행들이다. 실제 수업 질문의 반복률은 측정하지 않았다.
- 같은 프로세스에서 동시성 1 실행이 캐시를 채운 뒤 동시성 5를 실행해 동시성 5 행은 전부 적중이다.
- answers의 검색 결과 키는 limit=context_k(5)라 search(top_k 10)와 키가 다르다. 그래서 answers 동시성 1은 처음 27건이 `embed_hit`이다.
- 적중 경로도 원장 대조를 하므로 서버 total은 0.2ms 수준이다. 응답 지연의 나머지는 HTTP·JSON 직렬화다.
- RSS 증가(1976→2148MB)는 캐시 항목 수(질문 30개, 임베딩 약 1MB)보다 훨씬 커서 캐시 자체보다 프로세스 재기동·할당자 변동으로 본다.
  상한 추정은 ADR-008(임베딩 2000건 약 64MB).

### 10.2 항목별 확인

| 항목 | 결과 | 증거 |
|---|---|---|
| 1 구간 계측·baseline | `timings_ms`(scope·embed_query·keyword·vector·fusion·ledger_check·total, answers는 retrieval·generation·verify·total), `run_latency.py` | 위 표, `tests/unit/test_run_latency.py` |
| 2 클라이언트 재사용·병렬 | `AsyncQdrantClient`·`AsyncOpenSearch` 앱 전역 1개(`container.build_services`), hybrid `asyncio.gather`, `get_db` 요청당 세션 1개. 동시 질문 임베딩 batch 추가 | 표 1, `tests/unit/test_query_batcher.py` |
| 3 ingestion batch | 로컬 임베딩 32(`EMBEDDING_BATCH_SIZE`), OpenAI 100·429 backoff 1/2/4초, Qdrant upsert 64, OpenSearch bulk 200 — 설계값과 같음 | `vector.UPSERT_BATCH`, `keyword.BULK_BATCH`, `openai_emb.py` |
| 4 필터 인덱스 | `/health/ready` `qdrant_payload_indexes`=[collection_id, document_id, document_version, institution_id], `opensearch_keyword_fields`=[chunk_id, collection_id, document_id, institution_id] | 실제 엔진 ready 응답, `tests/integration/test_pipeline_live.py` |
| 5 후보·context 수 | 조정하지 않음. dev 세 모드가 이미 Hit@3=1.0이고, 지연은 후보 수가 아닌 임베딩이 지배 | `evaluation/results/m10_regression/` |
| 6 캐시 | 임베딩 → 검색 결과 순으로 켬. 답변 캐시는 미구현(ADR-008) | 표 2, `tests/api/test_cache.py` |

정확도 회귀 확인: 같은 데이터에서 `062ede3`과 `7f77d4a`(캐시 off)의 dev 30문항 세 모드 순위 페이지 목록이 30/30 동일했다.
M9 결과(문서 5개·46청크)와 hybrid Hit@1이 다른 것(1.0 → 0.9615, q007)은 코퍼스 차이(문서 2개·19청크, BM25 IDF 변화) 때문이다.

### 목표 대비

| 목표(계획서, warm·동시 1) | 결과 | 판단 |
|---|---|---|
| retrieval p50 0.8초·p95 1.5초 | 캐시 off p50 46ms·p95 56ms(네이티브 호스트) | 달성. 컨테이너(linux/arm64 CPU torch)에서는 미측정 |
| answer p50 5초·p95 10초 | fake provider로 46ms/52ms. 실제 LLM 지연 **미측정** | 미측정. 유료 키(OPENAI/ANTHROPIC)가 없어 실행하지 않음 |

다음 실험:
1. Docker 환경에서 같은 명령으로 컨테이너 수치와 `docker stats` 메모리(`EVAL_CONTAINER_MEMORY`)를 채운다.
2. 키가 생기면 `ANSWER_PROVIDER=claude|openai`로 `--endpoint answers --n 40 --concurrency 1`을 재고, 생성 단계(`timings_ms.generation`)가
   목표를 넘으면 context_k·max_output_tokens부터 줄인다.
3. 반복 없는 질문 집합(test split 등)으로 캐시 적중률이 낮은 경우를 따로 잰다.
4. 동시성이 더 높으면 임베딩이 병목이므로 e5-small(질문 11ms, M4 표) 또는 별도 임베딩 서버를 비교한다.

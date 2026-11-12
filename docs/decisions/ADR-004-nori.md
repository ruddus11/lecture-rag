# ADR-004 Nori 분석기 설정과 샘플 분석 결과, standard fallback

- 상태: 채택
- 날짜: 2026-11-12
- 관련: 설계서 4.3, `infra/opensearch/index-chunks.json`, `apps/api/app/retrieval/keyword.py`

## 확인 환경

Docker가 없어 OpenSearch 공식 `opensearch-min-2.19.7-linux-arm64.tar.gz`(sha512 `89f6cb7f…343daa` 대조)를 Temurin JDK 21.0.13(macOS aarch64, sha256 대조)로 실행하고 `analysis-nori-2.19.7.zip`을 설치했다(compose의 이미지와 같은 2.19.7·같은 플러그인). `_cat/plugins` → `analysis-nori 2.19.7`. 실행 스크립트는 `docs/handoff.md`.

## `_analyze` 결과 (`field: text`, analyzer `korean` = nori_tokenizer mixed + nori_part_of_speech + nori_readingform + lowercase)

설계서 초기 stoptags로 분석한 결과:

| 입력 | 토큰 |
|---|---|
| 운영체제 | 운영 \| 체제 |
| 스케줄링 알고리즘 | 스케줄링 \| 스케줄 \| 링 \| 알고리즘 |
| TCP 혼잡 제어 | tcp \| 혼잡 \| 제어 |
| 선점형 스케줄링과 비선점형 스케줄링의 차이는? | 선점 \| 스케줄링 \| 스케줄 \| 링 \| 선점 \| 스케줄링 \| 스케줄 \| 링 \| 차이 |
| 교착 상태가 발생하기 위한 네 가지 조건은? | 교착 \| 상태 \| 발생 \| 위한 \| 위하 \| 가지 \| 조건 |
| 라운드 로빈에서 시간 할당량이 너무 작으면 어떻게 되나? | 라운드 \| 로빈 \| 시간 \| 할당량 \| 할당 \| 량 \| 작 \| 되 |
| 이 경우에는 프로세스를 종료할 수 있다 | 경우 \| 프로세스 \| 종료 \| 수 \| 있 \| (이다 계열 포함 시 copula) |

품사 확인(`explain`): `수`=NNB(의존 명사), `이다`의 `이`=VCP, 보조 용언은 VX로 나온다. 이들은 검색어로서 정보가 거의 없고 거의 모든 문서에 나온다.

## 결정

1. stoptags에 `NNB`, `VCP`, `VCN`, `VX`를 추가한다. 조정 후 결과:
   - `이 경우에는 프로세스를 종료할 수 있다` → 경우 \| 프로세스 \| 종료 \| 있
   - `비선점형 스케줄링이다` → 비선점 \| 형 \| 스케줄링 \| 스케줄 \| 링
   - 나머지 5개 샘플은 위 표와 같다.
2. `VV`·`VA`(일반 동사·형용사, 예: `작`, `발생`)는 남긴다. "너무 작으면"처럼 의미를 가진 경우가 있어서다.
3. 알려진 한계: 문맥에 따라 `비선점형`이 `비/XPN + 선점`으로 나뉘어 `XPN` 제거로 `선점`만 남는다(질문 4번). 그래서 "선점형"과 "비선점형"을 nori 필드만으로는 구분하지 못한다. `text.std`(standard analyzer, 가중치 0.3) 하위 필드가 어절 그대로(`비선점형`) 색인하므로 정확 일치 시 보정된다. 이 이상은 평가(M9) 결과를 보고 판단한다.
4. `decompound_mode: mixed` 유지. `스케줄링`과 `스케줄`·`링`이 함께 나와 부분 일치 재현율이 오른다(`링` 같은 잡음 토큰은 감수).
5. Nori가 없으면 `/health/ready`가 503 + `keyword_analyzer_missing`. `KEYWORD_ANALYZER=standard`로만 기동을 허용하며, 이때 인덱스 이름은 `chunks_v1_standard`(analysis 설정 없이 `text` analyzer=standard)로 분리한다. 같은 이름을 쓰면 analyzer가 다른 기존 인덱스와 섞이기 때문이다(설계서 4.3의 "인덱스 하나"에서 달라진 점). `/search` 응답과 평가 결과에 `keyword_analyzer`를 표기한다.
6. BM25 파라미터는 기본값(k1=1.2, b=0.75).

## 기타

- 로컬 macOS 실행 인스턴스는 디스크 사용률이 97%라 flood-stage 워터마크로 인덱스 생성이 막혀, 이 테스트 인스턴스에만 `cluster.routing.allocation.disk.threshold_enabled=false`를 설정했다. compose 구성에는 넣지 않는다.
- 검증 테스트: `tests/integration/test_pipeline_live.py::test_nori_analyzer_live`.

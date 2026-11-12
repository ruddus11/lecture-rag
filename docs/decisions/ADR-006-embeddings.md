# ADR-006 로컬 임베딩 기본(bge-m3)과 OpenAI 선택, 컬렉션 명명

- 상태: 채택
- 날짜: 2026-11-12
- 관련: 설계서 4.2, 5.4, 6.2, `apps/api/app/retrieval/{embeddings/*,vector.py}`, `app/container.py`

## 결정

- 기본 `EMBEDDING_PROVIDER=local`, `EMBEDDING_MODEL=BAAI/bge-m3`(1024차원, `normalize_embeddings=True`, `max_seq_length=1024`, CPU). 키 없이 전체 흐름이 돈다.
- 빠른 개발용 대안 `intfloat/multilingual-e5-small`(384차원). 모델 이름에 `e5`가 있으면 문서 `passage: `, 질문 `query: ` 접두어를 자동으로 붙인다.
- `openai`: `text-embedding-3-small`(1536), `dimensions` 미사용, batch 100, `RateLimitError`는 1·2·4초 backoff 3회 뒤 `embedding_rate_limited`. SDK 자체 재시도는 끈다(`max_retries=0`, 재시도 정책을 한 곳에서만 갖기 위해).
- Qdrant 컬렉션 `chunks__{model_slug}__{dim}`. `model_slug`는 마지막 경로 요소를 소문자·`[^a-z0-9]→_`로 바꾼 값(`BAAI/bge-m3`→`bge_m3`). 모델을 바꾸면 컬렉션이 바뀌고, ready 문서가 있는데 현재 컬렉션이 비어 있으면 `/health/ready`가 `warnings:["reindex_required"]`를 낸다(503은 아님). 재색인은 `python -m scripts.reindex`.
- 컬렉션 생성 직후 payload index 4개(`institution_id`·`collection_id`·`document_id` keyword, `document_version` integer). 이미 있는 컬렉션도 기동·ready 때 빠진 index를 보충한다. `/health/ready`의 `checks.qdrant_payload_indexes`로 확인한다.
- 문서 임베딩 해시 캐시: `/data/emb_cache/{model_slug}/{sha256[:2]}/{sha256}.npy`(float32). 손상 파일은 미적중으로 다시 계산한다. 질문 임베딩 캐시(TTLCache)는 M10.
- `index_profiles`에 `(provider, model, dim, chunker, parser, qdrant 컬렉션, opensearch 인덱스)`를 기동 시 1행 기록하고 `/meta.index_profile`로 노출한다.
- 질문 임베딩은 `asyncio.to_thread`로 실행하고 15초 상한(모델 적재 대기 포함)을 둔다. 엔진 호출 자체는 `SEARCH_ENGINE_TIMEOUT_MS`(2초).

## 검증

- 테스트는 qdrant-client 로컬 모드(`QdrantStore(":memory:")`)를 실제 어댑터로 쓴다. 로컬 모드는 payload index가 효과가 없으므로 index 존재 확인은 실제 서버에서 한다.
- 구현 머신에 Docker가 없어 Qdrant 공식 macOS arm64 바이너리 v1.20.0(compose와 같은 버전, GitHub release `qdrant-aarch64-apple-darwin.tar.gz`, sha256 `531904e8…331b20a`)을 `.tools/qdrant`에 두고 실제 서버로 확인했다. 결과는 `docs/performance.md`와 `docs/handoff.md`.

## 결과

- bge-m3는 CPU 색인이 느리다(실측은 performance.md). 개발 루프에서는 e5-small로 바꾸고 재색인한다.
- 질문과 문서는 항상 같은 provider·모델로 임베딩된다(컨테이너 단일 설정).

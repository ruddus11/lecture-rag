#!/bin/zsh
# 로컬 검증용 API 기동 (Docker 없이). 인자: 포트(기본 8010), 임베딩 모델(기본 BAAI/bge-m3)
R="${0:A:h:h:h}"
cd "$R/apps/api"
export APP_ENV=dev DATA_DIR="$R/.tools/e2e/data" QDRANT_URL=http://127.0.0.1:6333 OPENSEARCH_URL=http://127.0.0.1:9200 \
  INSTITUTIONS_FILE="$R/config/institutions.yaml" USERS_FILE="$R/config/users.yaml" \
  HF_HOME="$R/.tools/hf_cache" HF_HUB_OFFLINE=1 TIKTOKEN_CACHE_DIR="$R/.tools/tiktoken" \
  EMBEDDING_MODEL="${2:-BAAI/bge-m3}" KEYWORD_ANALYZER="${KEYWORD_ANALYZER:-korean}" \
  ANSWER_PROVIDER="${ANSWER_PROVIDER:-fake}" RATE_LIMIT_ENABLED=false \
  APP_COMMIT=$(git rev-parse --short HEAD) AUTH_SECRET=local-e2e-secret-0123456789abcdefghij
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "${1:-8010}" --workers 1

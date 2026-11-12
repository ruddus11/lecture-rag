# Docker 없이 로컬에서 엔진 띄우기 (macOS arm64 검증용)

구현 머신에 Docker가 없어 compose와 **같은 버전**의 엔진을 네이티브로 띄워 integration 테스트와 e2e를 확인했다.
운영·데모 경로는 `docker compose up`이며, 이 폴더는 개발 검증용이다. 바이너리와 데이터는 `.tools/`(gitignore)에 둔다.

| 엔진 | 받는 파일 | 검증 |
|---|---|---|
| Qdrant 1.20.0 | GitHub release `qdrant-aarch64-apple-darwin.tar.gz` | sha256 `531904e822050790bb8c1da6705f801ee48b91eb4c229d0d605ff06f6331b20a` |
| OpenSearch 2.19.7 | `artifacts.opensearch.org/.../opensearch-min-2.19.7-linux-arm64.tar.gz` + `analysis-nori-2.19.7.zip` | 배포처 `.sha512`와 대조 |
| JDK | Adoptium Temurin 21.0.13+9 macOS aarch64 | Adoptium API sha256 대조 |

```bash
infra/local/engines.sh start      # 127.0.0.1:6333(qdrant), 127.0.0.1:9200(opensearch)
infra/local/api.sh 8010           # uvicorn, DATA_DIR=.tools/e2e/data, bge-m3 (두 번째 인자로 모델 변경)
cd apps/api && uv run python -m scripts.e2e_smoke --base http://127.0.0.1:8010/api/v1 --modes keyword,vector,hybrid
cd apps/api && uv run pytest -m integration
infra/local/engines.sh stop
```

디스크 사용률이 95%를 넘으면 OpenSearch가 인덱스 생성을 막는다. 이 로컬 인스턴스에서만 `engines.sh`가 디스크 워터마크 검사를 끈다.

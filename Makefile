# 단축 명령. 호스트 테스트는 apps/api 의 uv 가상환경과 apps/web 의 node_modules 를 쓴다.
API := apps/api
WEB := apps/web

.PHONY: up down logs ps test test-api test-web lint eval env

env:
	@test -f .env || cp .env.example .env

up: env
	APP_COMMIT=$$(git rev-parse --short HEAD 2>/dev/null || echo unknown) docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

ps:
	docker compose ps

test: test-api test-web

test-api:
	cd $(API) && uv run pytest -q

test-web:
	cd $(WEB) && npm test

lint:
	cd $(API) && uv run ruff check . && uv run ruff format --check . && uv run mypy app
	cd $(WEB) && npm run lint && npm run typecheck

eval:
	docker compose exec api python -m evaluation.run_retrieval --split dev --modes keyword,vector,hybrid --top-k 10 --out evaluation/results

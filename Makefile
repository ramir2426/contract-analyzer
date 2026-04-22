.PHONY: dev prod build test lint format typecheck setup-ollama ci logs

dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up

prod:
	docker compose up -d

build:
	docker compose build

test:
	pytest tests/ -v

lint:
	ruff check app/ tests/
	ruff format --check app/ tests/

format:
	ruff format app/ tests/

typecheck:
	mypy app/

setup-ollama:
	docker compose exec ollama ollama pull llama3.2
	docker compose exec api python scripts/index_legal_docs.py

ci: lint typecheck test

logs:
	docker compose logs -f api

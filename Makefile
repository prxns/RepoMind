.PHONY: install dev test lint format typecheck build evaluate

install:
	python -m pip install -e "apps/api[dev,local]"
	cd apps/web && npm install

dev:
	docker compose up --build

test:
	cd apps/api && python -m pytest
	cd apps/web && npm test

lint:
	cd apps/api && ruff check .
	cd apps/web && npm run lint

format:
	cd apps/api && ruff format .

typecheck:
	cd apps/api && mypy repomind --ignore-missing-imports
	cd apps/web && npm run typecheck

build:
	cd apps/web && npm run build

evaluate:
	PYTHONPATH=apps/api python evals/run.py

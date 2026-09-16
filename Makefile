.PHONY: install dev test lint typecheck build evaluate

install:
	python -m pip install -e "apps/api[dev,local]"
	cd apps/web && npm install

dev:
	docker compose up --build

test:
	cd apps/api && python -m pytest
	cd apps/web && npm test

lint:
	cd apps/api && ruff check . && ruff format --check .
	cd apps/web && npm run lint

typecheck:
	cd apps/api && mypy repomind
	cd apps/web && npm run typecheck

build:
	cd apps/web && npm run build

evaluate:
	PYTHONPATH=apps/api python evals/run.py

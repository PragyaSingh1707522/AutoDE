.PHONY: up down test lint typecheck
up:
	docker compose up --build
down:
	docker compose down
test:
	python -m pytest backend/tests
lint:
	python -m ruff check backend
typecheck:
	python -m mypy backend/app backend/seed_demo.py

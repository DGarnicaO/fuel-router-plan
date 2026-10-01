EXEC = docker compose exec web

.PHONY: up down migrate seed test lint fmt lock

up:
	docker compose up -d --build

down:
	docker compose down

migrate:
	$(EXEC) python manage.py migrate

seed: migrate
	$(EXEC) python manage.py load_cities data/2025_Gaz_place_national.txt
	$(EXEC) python manage.py load_fuel_prices data/fuel-prices.csv

test:
	$(EXEC) pytest

lint:
	$(EXEC) ruff check .
	$(EXEC) ruff format --check .

fmt:
	$(EXEC) ruff check --fix .
	$(EXEC) ruff format .

lock:
	docker run --rm -v "$(CURDIR):/app" -w /app ghcr.io/astral-sh/uv:0.12.21-python3.14-trixie-slim uv lock

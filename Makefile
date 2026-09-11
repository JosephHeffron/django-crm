.PHONY: setup dev test lint security migrate shell check build arm64 backup

VENV := .venv/bin

setup:
	python -m venv .venv
	$(VENV)/pip install --upgrade pip
	$(VENV)/pip install -r requirements.txt -r requirements-dev.txt

dev:
	$(VENV)/python manage.py runserver

test:
	$(VENV)/python manage.py test

lint:
	$(VENV)/ruff check .
	$(VENV)/ruff format --check .

security:
	$(VENV)/pip-audit -r requirements.txt
	$(VENV)/bandit -r apps config -x '*/tests/*,*/migrations/*'

migrate:
	$(VENV)/python manage.py migrate

shell:
	$(VENV)/python manage.py shell

check:
	$(VENV)/python manage.py check
	$(VENV)/python manage.py makemigrations --check --dry-run

# Not implemented yet — these belong to later roadmap phases and would
# otherwise silently no-op instead of honestly failing.
build:
	@echo "make build: not implemented until the Containerization phase (see docs/ROADMAP.md)"; exit 1

arm64:
	@echo "make arm64: not implemented until the ARM64 deployment phase (see docs/ROADMAP.md)"; exit 1

backup:
	@echo "make backup: not implemented until the Backups/disaster recovery phase (see docs/ROADMAP.md)"; exit 1

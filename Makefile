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

build:
	podman build -t django-crm -f Containerfile .

# Validates ARM64 compatibility under qemu-user-static emulation — see
# docs/ARM64_REVIEW.md/docs/ARM64_TESTING.md. Not a substitute for
# testing on real Raspberry Pi hardware, which this project doesn't
# have yet.
arm64:
	./scripts/test-arm64.sh

# Runs against the real production stack (compose.prod.yml) by
# default — see docs/ADMIN_GUIDE.md's "Backups" section, and
# scripts/backup.sh's own header comment for the environment
# variables that let this target run against a throwaway stack
# instead.
backup:
	./scripts/backup.sh

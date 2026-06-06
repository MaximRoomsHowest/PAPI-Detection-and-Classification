# One-command developer tasks (audit IMP-DX-1). `make check` mirrors the
# non-Docker CI gates; use `make docker-build` for the image-build gate.
# Recipe lines are tab-indented (Make requires it).
.PHONY: help install lint test build docker-build check deliverables-check

help:
	@echo "Targets:"
	@echo "  install             install backend + papi + frontend deps"
	@echo "  lint                ruff + eslint"
	@echo "  test                pytest (papi + backend) + vitest"
	@echo "  build               build the frontend bundle"
	@echo "  docker-build        build backend + frontend images"
	@echo "  check               lint + test + build (non-Docker CI gates)"
	@echo "  deliverables-check  fail on unfilled TEAM/TODO/TBD markers"

install:
	pip install -e .[dev]
	pip install -r apps/backend/requirements-dev.txt
	cd apps/frontend && npm install
	pre-commit install

lint:
	ruff check apps/backend packages/papi workflows/scripts
	cd apps/frontend && npm run lint

test:
	pytest packages/papi/tests
	cd apps/backend && pytest
	cd apps/frontend && npm test

build:
	cd apps/frontend && npm run build

docker-build:
	docker compose build backend frontend

deliverables-check:
	pwsh scripts/build-deliverables.ps1 -CheckOnly -Strict

check: lint test build

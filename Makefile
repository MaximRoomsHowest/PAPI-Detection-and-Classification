# One-command developer tasks (audit IMP-DX-1). Mirrors the CI gates so
# `make check` locally == green CI. Recipe lines are tab-indented (Make requires it).
.PHONY: help install lint test build check deliverables-check

help:
	@echo "Targets:"
	@echo "  install             install backend + papi + frontend deps"
	@echo "  lint                ruff + eslint"
	@echo "  test                pytest (papi + backend) + vitest"
	@echo "  build               build the frontend bundle"
	@echo "  check               lint + test (the CI gate)"
	@echo "  deliverables-check  fail on unfilled TEAM/TODO/TBD markers"

install:
	pip install -e .[dev]
	pip install -r apps/backend/requirements.txt
	cd apps/frontend && npm install

lint:
	ruff check apps/backend packages/papi workflows/scripts
	cd apps/frontend && npm run lint

test:
	pytest packages/papi/tests
	cd apps/backend && pytest
	cd apps/frontend && npm test

build:
	cd apps/frontend && npm run build

deliverables-check:
	pwsh scripts/build-deliverables.ps1 -CheckOnly -Strict

check: lint test

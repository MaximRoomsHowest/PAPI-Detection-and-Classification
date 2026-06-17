# One-command developer tasks (audit IMP-DX-1). `make check` mirrors the
# non-Docker CI gates; use `make docker-build` for the image-build gate.
# Recipe lines are tab-indented (Make requires it).
.PHONY: help install lint test build docker-build check deliverables-check up down logs backup restore

help:
	@echo "Targets:"
	@echo "  install             install backend + papi + frontend deps"
	@echo "  lint                ruff + eslint"
	@echo "  test                pytest (papi + backend) + vitest"
	@echo "  build               build the frontend bundle"
	@echo "  docker-build        build backend + frontend images"
	@echo "  check               lint + test + build (non-Docker CI gates)"
	@echo "  deliverables-check  fail on unfilled TEAM/TODO/TBD markers"
	@echo "  up                  docker compose up -d --build (full local stack)"
	@echo "  down                docker compose down (KEEPS data volumes)"
	@echo "  logs                follow backend + frontend + db logs"
	@echo "  backup              tar the data volumes into ./backups (run 'make down' first)"
	@echo "  restore             restore the data volumes from ./backups"

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

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

# Back up the persistent named volumes (Postgres history + uploads/exports + model-lifecycle
# stores) into ./backups via a throwaway alpine container, addressed through the pinned
# container_names so the compose project prefix is irrelevant. The papi-* containers must EXIST:
# for a consistent snapshot run `docker compose stop` first (NOT `down`, which removes the
# containers --volumes-from needs), then `docker compose start` after. NOTE: only
# `docker compose down -v` wipes these volumes — always `make backup` before running that.
backup:
	@mkdir -p backups
	docker run --rm --volumes-from papi-postgres -v "$(CURDIR)/backups:/backup" alpine \
		tar czf /backup/papi-postgres.tgz -C / var/lib/postgresql
	docker run --rm --volumes-from papi-backend -v "$(CURDIR)/backups:/backup" alpine \
		tar czf /backup/papi-storage.tgz -C / storage user_models datasets jobs
	@echo "Backed up DB + storage to ./backups/ (papi-postgres.tgz, papi-storage.tgz)."

# Restore the volumes from ./backups. Stop the app first so nothing writes mid-restore, but keep
# the containers (so --volumes-from resolves): `docker compose stop` -> `make restore` ->
# `docker compose start` (or `make up`).
restore:
	docker run --rm --volumes-from papi-postgres -v "$(CURDIR)/backups:/backup" alpine \
		sh -c "cd / && tar xzf /backup/papi-postgres.tgz"
	docker run --rm --volumes-from papi-backend -v "$(CURDIR)/backups:/backup" alpine \
		sh -c "cd / && tar xzf /backup/papi-storage.tgz"
	@echo "Restored DB + storage from ./backups/. Restart with: docker compose start (or make up)."

deliverables-check:
	pwsh scripts/build-deliverables.ps1 -CheckOnly -Strict

check: lint test build

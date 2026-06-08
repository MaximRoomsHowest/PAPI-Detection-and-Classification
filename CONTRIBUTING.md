# Contributing

This is a Howest CTAI industry project (2025-26) for Intersoft Electronics. These
notes keep the four-person team — and any future maintainer — consistent.

## Setup

Full details are in `README.md` and `docs/installation-manual.md`. In short:

- Python: create a venv, then `pip install -e .[dev]` and
  `pip install -r apps/backend/requirements-dev.txt` (the `-dev` set adds `httpx2`,
  which the backend test client needs).
- Frontend: `cd apps/frontend && npm install`.
- Optional full stack: `docker compose up -d --build` (see `.env.example`).

## Before you push

CI gates on all of these, so run them locally first:

- `ruff check apps/backend packages/papi workflows/scripts`
- `pytest packages/papi/tests`
- `pytest` inside `apps/backend`
- `npm run lint`, `npm test`, `npm run build` inside `apps/frontend`

Before submitting deliverables, also run
`pwsh scripts/build-deliverables.ps1 -CheckOnly -Strict` to confirm no
`<!-- TEAM -->` / `[TODO]` markers remain.

## Conventions

- Backend: FastAPI + SQLAlchemy 2.0, layered `routes -> services -> repositories`.
- ML library (`packages/papi`) stays pure and dependency-light; import from the
  package root (`from papi import ...`).
- Geometry/airport data lives in `configs/*.yaml`; model lineage in
  `models/MODELS.md`; never hand-type training metrics — regenerate them with
  `workflows/scripts/populate_model_metrics.py`.
- Keep commit messages short and descriptive.
- Don't commit model weights or datasets except at the canonical whitelisted
  paths (see `.gitignore`).

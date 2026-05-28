---
title: "PAPI Vision — Technical Components Overview"
subtitle: "Howest Industry Project · Intersoft Electronics Services BV · 2026"
geometry: "a4paper, margin=1.5cm"
fontsize: 10pt
mainfont: "Calibri"
---

# PAPI Vision — Technical Components Overview

> One A4 page (Leho deliverable #8). Distil of [architecture-overview.md](../architecture-overview.md) for the final-submission packet.

## System diagram

```
   DJI Matrice 4E drone                 Browser (jury / reviewer)
   │ JPGs + EXIF + DJI XMP              │ Chrome · Firefox · Edge · Safari
   ▼                                    ▼
┌──────────────────────────┐    ┌────────────────────────────────────┐
│ OFFLINE pipeline         │    │ ONLINE stack (Docker compose)      │
│ workflows/scripts/       │    │                                    │
│   pipeline.py            │    │  Nginx :8080  ──► React/Vite SPA   │
│                          │    │   (unprivileged, non-root)         │
│ extract → calibrate →    │    │            │                       │
│ autolabel → sample →     │    │            │ fetch /api/*          │
│ export → train (YOLO)    │    │            ▼                       │
│                          │    │  FastAPI :8000  ──► YOLO (.pt)     │
│ Inputs:  data/raw/       │    │   (uvicorn, non-root, X-API-Key)   │
│ Outputs: configs/        │    │            │                       │
│          projection.yaml │    │            ▼                       │
│          models/serving/ │    │  Postgres 16 :5434                 │
│          best.pt         │    │   (127.0.0.1 only, healthcheck)    │
└──────────────────────────┘    │   table: analysis_logs             │
            │                   └────────────────────────────────────┘
            └── trained weights ───────► models/serving/best.pt
```

## Components

| Component | Role | Language / framework | Where |
|---|---|---|---|
| Drone capture | Data source | DJI M4E + XMP EXIF | client-owned |
| Offline ML pipeline | Calibration + auto-labels + training | Python 3.10, Ultralytics YOLO | `workflows/scripts/` |
| `papi` package | Pure-Python ML/geom library (no I/O) | Python | `packages/papi/src/papi/` |
| Backend API | Inference + persistence + endpoints | FastAPI 0.115 + SQLAlchemy 2.0 | `apps/backend/` |
| Database | Analysis logs (one row / request) | Postgres 16 | `docker-compose.yml` |
| Frontend SPA | Demo + Insights + History UI | React 19 + Vite 8 + Plotly | `apps/frontend/` |
| Reverse proxy | TLS termination + SPA fallback | Nginx (unprivileged) | `apps/frontend/Dockerfile` |
| CI | Lint + tests + Docker build | GitHub Actions | `.github/workflows/ci.yml` |

## Data flow per analysis request

1. Browser uploads frame(s) + drone metadata to `POST /api/analyze*`.
2. FastAPI saves bytes to `/storage/uploads/`, computes per-lamp elevation angles from drone GPS + surveyed lamp coords in `configs/papi_edny.yaml`.
3. YOLO predicts → `[Detection]` with class (red / white) + bbox + conf.
4. `state.normalize_detections` promotes borderline lamps to *transition* via geometry (no learned transition class).
5. `global_state_from_lamps` derives one of five PAPI patterns.
6. Annotated artifact written to `/storage/exports/`; one row to `analysis_logs`; upload bytes deleted; JSON returned.
7. `/insights` reads aggregated stats from `GET /api/stats`; `/history` reads `GET /api/logs`.

## Why these technologies

- **FastAPI** — async + Pydantic v2 + free OpenAPI docs for the jury.
- **Postgres** — transactional, native UUID/JSON, free; no NoSQL data shape required.
- **YOLO (Ultralytics)** — de-facto standard for one-shot detection with an INT8-ONNX edge-export path already available.
- **React 19 + Vite 8** — team familiarity, fast HMR, mature ecosystem for charts (Plotly) and PDF export (jsPDF).
- **Docker compose** — single-command `docker compose up -d --build` from a clean machine; reproducible for any jury member.

*Full design rationale, scope limits and open questions in [architecture-overview.md](../architecture-overview.md). Source of truth for components, ports, healthchecks and security floor: [docker-compose.yml](../../docker-compose.yml).*

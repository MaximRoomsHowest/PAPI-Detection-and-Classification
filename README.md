# PAPI Detection and Classification

[![CI](https://github.com/MaximRoomsHowest/PAPI-Detection-and-Classification/actions/workflows/ci.yml/badge.svg)](https://github.com/MaximRoomsHowest/PAPI-Detection-and-Classification/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Node 20](https://img.shields.io/badge/node-20-green.svg)](https://nodejs.org/)

Real-time detection of a four-light **PAPI** (Precision Approach Path Indicator)
installation and per-lamp **white / red / transition** state classification from
DJI Matrice 4E drone imagery. Howest industry project for **Intersoft Electronics
Services BV**, May–June 2026.

## Setup

Requires **Python 3.10+**.

```powershell
py -3.10 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

## Link The Raw Dataset

The pipeline reads images from `data/raw/<flight>/<file>.JPG`. To avoid copying
the archived raw dataset, create a Windows directory junction from `data/raw`
to the archived artifact folder:

```powershell
cmd /c mklink /J data\raw ..\PAPI-artifacts\2026-05-26-cleanup\PROJECT1-PAPI
```

The canonical corrected sequence dataset is archived under:

```text
..\PAPI-artifacts\2026-05-26-cleanup\data\datasets\papi_lamp_sequences\
```

## Run The ML Pipeline

One entrypoint: `workflows/scripts/pipeline.py` with five named stages. Run them all in
order, or target an individual stage:

```powershell
python workflows/scripts/pipeline.py all
python workflows/scripts/pipeline.py all --skip export
python workflows/scripts/pipeline.py autolabel --limit 100
python workflows/scripts/pipeline.py export --limit 300
```

For active-learning preprocessing and training workflows, use the notebooks:

- `workflows/notebooks/02_active_learning_preprocessing_template.ipynb`
- `workflows/notebooks/03_yolov26n_detection_tracking_training.ipynb`
- `workflows/notebooks/04_yolov26n_sequence_model_evaluation.ipynb`

For the current detector scope, use two classes only:
`papi_light_red` and `papi_light_white`. Transitions are inferred later by
tracking each individual lamp over time.

## Run The Integrated App

Local model binaries live outside Git under `models/`.

```powershell
# from the repo root
Copy-Item models\base\yolo26n.pt models\serving\best.pt -Force

# terminal 1: backend
cd apps\backend
copy .env.example .env
docker compose up -d
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# terminal 2: frontend
cd apps\frontend
copy .env.example .env
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173/live-demo`, keep **Backend API** selected, and pick
one of three upload paths:

- **Single image**: frontend calls `POST /api/analyze-frame`.
- **Video**: frontend calls `POST /api/analyze`.
- **Folder of images**: frontend extracts files client-side and calls
  `POST /api/analyze-frames` to batch-analyze every image in one request.

All endpoints accept optional drone metadata fields (`runway_id`, `drone_id`,
`drone_latitude`, `drone_longitude`, `drone_altitude_m`) and respect
`VITE_PAPI_API_URL` / `VITE_PAPI_API_KEY` env vars.

## Test Videos

Small generated smoke-test videos live in `test_videos/`. They are derived from
the archived sequence dataset and are intended for frontend/backend upload
testing, not for model training.

## Repository Layout

Start here when looking for a part of the project:

- App work lives in `apps/`: FastAPI backend in `apps/backend/`, React frontend in `apps/frontend/`.
- Reusable ML/data Python code lives in `packages/papi/`.
- Human-facing ML workflows live in `workflows/`: notebooks in `workflows/notebooks/`, runnable data scripts in `workflows/scripts/`.
- Shared project inputs stay at the root: `configs/`, `data/`, `models/`, `docs/`, and `test_videos/`.

| Path | Purpose |
|---|---|
| `apps/backend/` | FastAPI backend for upload analysis, result logs, and annotated artifact serving. |
| `apps/frontend/` | Vite/React dashboard with Backend API mode and Mock mode. |
| `packages/papi/src/papi/` | Python package: metadata, geometry, projection, lamp-state, sampling, CVAT export, YOLO I/O. |
| `packages/papi/tests/` | Root `pytest` suite for ML/data code. |
| `workflows/scripts/` | Runnable ML/data entrypoints. |
| `workflows/notebooks/` | Notebook-first ML workflows. |
| `models/` | Ignored local model weights. `models/base/` holds base weights; `models/serving/best.pt` is the backend runtime model. |
| `test_videos/` | Small MP4 fixtures for end-to-end upload smoke tests. |
| `..\PAPI-artifacts\2026-05-26-cleanup\PROJECT1-PAPI/` | Archived raw dataset. Do not modify. |
| `data/raw/` | Optional local junction to the archived raw dataset. |
| `..\PAPI-artifacts\2026-05-26-cleanup\data\datasets\papi_lamp_sequences/` | Archived canonical corrected sequence dataset and tracking artifacts. |
| `data/README.md` | Data organization rules and current sequence dataset workflow. |
| `configs/` | PAPI coordinates, split config, and projection config. |
| `docs/` | Annotation conventions and pipeline documentation. |

## Verification

Recommended checks before committing:

```powershell
.venv\Scripts\python.exe -m pytest packages/papi/tests
.venv\Scripts\python.exe -m ruff check packages/papi workflows/scripts apps/backend
cd apps\backend; ..\..\.venv\Scripts\python.exe -m pytest
cd apps\frontend; npm run lint
cd apps\frontend; npm run build
```

## Notes

- Day flights target the runway 24 PAPI; night flights target runway 06.
- EDNY exact set-angles and lamp WGS84 altitudes still need Intersoft
  confirmation.

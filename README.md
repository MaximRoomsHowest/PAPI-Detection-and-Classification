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

- `workflows/notebooks/02_model_assisted_labelling.ipynb`
- `workflows/notebooks/03_yolov26n_detection_tracking_training.ipynb`
- `workflows/notebooks/04_yolov26n_sequence_model_evaluation.ipynb`

For the current detector scope, use two classes only:
`papi_light_red` and `papi_light_white`. Transitions are inferred later by
tracking each individual lamp over time.

## Run The Integrated App

The serving weights (`models/serving/best.pt`) ship in the repo; seed the slot
from a base weight only if it is missing:

```powershell
# from the repo root, only if models/serving/best.pt is absent
Copy-Item models\base\yolo26s.pt models\serving\best.pt -Force
```

**Full stack with Docker (recommended)** — Postgres + backend + frontend in one go:

```powershell
# from the repo root
Copy-Item .env.example .env   # set POSTGRES_PASSWORD etc. before any real deploy
docker compose up -d --build
```

For native development (Postgres in Docker, backend + frontend run locally),
follow the step-by-step path in
[`docs/installation-manual.md`](docs/installation-manual.md).

Open `http://127.0.0.1:5173/live-demo`, keep **Backend API** selected, and pick
one of three upload paths:

- **Single image** (`Upload media`): frontend calls `POST /api/analyze-frame`.
- **Video** (`Upload media`): frontend uploads the whole clip to `POST /api/analyze`;
  the backend decodes the frames and returns one annotated video.
- **Folder of images** (`Upload folder`): frontend uploads every image in one
  request to `POST /api/analyze-sequence`, which treats the folder as an ordered
  image sequence — consecutive frames of a single clip — and returns **one
  time-sequenced annotated video** plus an aggregated verdict (the same tracked
  pipeline as a real video upload, not an independent-frame batch). Images are
  ordered by filename so a `frame_000.jpg … frame_NNN.jpg` capture sequence plays
  in order; playback speed is set by `PAPI_SEQUENCE_FPS` (default 4 fps). The
  batch endpoint `POST /api/analyze-frames` (independent per-image results) is
  still served for callers that want one row per image.

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
| `apps/frontend/` | Vite/React dashboard that calls the FastAPI backend for upload analysis, insights, and history. |
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

## Documentation

- **Architecture**: [`docs/architecture-overview.md`](docs/architecture-overview.md)
- **User manual**: [`docs/user-manual.md`](docs/user-manual.md) · **Install manual**: [`docs/installation-manual.md`](docs/installation-manual.md)
- **Pipeline**: [`docs/pipeline.md`](docs/pipeline.md) · **Label spec**: [`docs/label_spec.md`](docs/label_spec.md)
- **Model card**: [`docs/model-card.md`](docs/model-card.md) · **Data card**: [`docs/data-card.md`](docs/data-card.md)
- **Model registry**: [`models/MODELS.md`](models/MODELS.md) · **Edge benchmark**: [`docs/edge-benchmark.md`](docs/edge-benchmark.md)
- **Deliverables board** (submission tracker): [`docs/deliverables/README.md`](docs/deliverables/README.md)
- **Security policy**: [`SECURITY.md`](SECURITY.md) · **Contributing**: [`CONTRIBUTING.md`](CONTRIBUTING.md)

**License**: see [`LICENSE`](LICENSE) — terms are pending confirmation with
Intersoft, and the file records the Ultralytics **AGPL-3.0** dependency
obligation (see also [`SECURITY.md`](SECURITY.md)).

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

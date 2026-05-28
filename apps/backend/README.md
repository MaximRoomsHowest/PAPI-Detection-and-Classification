# PAPI Backend

Local-only FastAPI backend trial for immediate PAPI image/video analysis with database-backed result logs.

## Setup

For full-stack local development use the **root** docker-compose, which
brings up Postgres + this backend + the React frontend together. From
the repo root:

```powershell
cp .env.example .env             # adjust POSTGRES_PASSWORD etc.
docker compose up -d --build
```

To iterate on backend code without rebuilding the container on every
change, run just Postgres in Docker and uvicorn on the host:

```powershell
docker compose up -d postgres
cd apps/backend
..\..\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API will run at `http://127.0.0.1:8000`. Interactive docs at
`http://127.0.0.1:8000/docs`.

## Model

The serving model lives at:

```text
../../models/serving/best.pt
```

This file is tracked in Git via Git LFS-like whitelisted patterns in the
root `.gitignore` (see lines 67-72 there). For local smoke testing without
a trained model, copy a base weight into the serving slot:

```powershell
Copy-Item ..\..\models\base\yolo26n.pt ..\..\models\serving\best.pt -Force
```

For project-quality demos, replace `models/serving/best.pt` with the intended trained PAPI checkpoint.

## Endpoints

- `GET /health`
- `POST /api/analyze`
- `POST /api/analyze-frame`
- `POST /api/analyze-frames`
- `GET /api/logs`
- `GET /api/logs/{id}`
- `GET /api/runways`

`POST /api/analyze` accepts a form upload named `file`, plus optional `runway_id`, `drone_id`, `drone_latitude`, `drone_longitude`, and `drone_altitude_m`.

For the frontend video workflow, use `POST /api/analyze-frame`: the frontend splits video into image frames and sends each frame with drone metadata. The backend then runs exactly two tasks for that frame:

1. YOLO inference on the image to decide lamp states and global PAPI state.
2. Angle calculation from the submitted drone metadata and selected runway coordinates.

`POST /api/analyze-frames` is the batch variant: accepts a multipart upload named `files` (plural) with multiple image files plus the same optional drone metadata. The backend processes each image with the same per-frame logic and returns a single `FrameBatchPayload` aggregating per-frame results plus total processing time. This powers the frontend folder-upload workflow.

The single-frame endpoints return their results immediately and store a lightweight database log with result metadata, not the uploaded image/video bytes. Uploaded originals are deleted after processing; annotated exports stay in `storage/exports`.

## Structure

```text
app/
  api/              FastAPI route definitions
  models/           SQLAlchemy database entities
  repositories/     Database read/write logic
  services/         Inference, media, angle, runway, and state logic
  validation/       Pydantic schemas and request validation helpers
  config.py         Environment/settings loading
  database.py       Database engine/session setup
  main.py           FastAPI app entrypoint
../../models/
  serving/best.pt   Ignored local backend model loaded by default
```

## Angle Calculation

When uploaded media contains GPS latitude, longitude, and altitude metadata, or when those values are sent manually in the form data, the backend calculates the drone elevation angle using the same formula from the data-analysis notebook:

```text
distance = haversine(drone_lat, drone_lon, light_lat, light_lon)
angle = degrees(atan2(drone_alt - light_alt, distance))
```

If metadata is missing, the API returns `angle_available: false` instead of inventing a degree. Since frontend-generated frame images may not preserve original drone EXIF/telemetry, the frontend should send `drone_latitude`, `drone_longitude`, and `drone_altitude_m` with each frame whenever possible.

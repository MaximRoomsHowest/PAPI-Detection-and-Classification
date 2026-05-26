# PAPI Backend

Local-only FastAPI backend trial for immediate PAPI image/video analysis with database-backed result logs.

## Setup

From the repository root, the easiest local full-stack start is:

```bash
docker compose up --build
```

That starts PostgreSQL, FastAPI, and the React frontend together.

For backend-only development:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d postgres
python -m uvicorn app.main:app
```

The API will run at `http://127.0.0.1:8000`.

## Model

Backend-only runs expect the local model at:

```text
models/best.pt
```

This file is intentionally ignored by Git. The root Docker Compose flow mounts the model directly from:

```text
../data/runs/detect/train-3/weights/best.pt
```

## Endpoints

- `GET /health`
- `POST /api/analyze`
- `POST /api/analyze-frame`
- `GET /api/logs`
- `GET /api/logs/{id}`
- `GET /api/runways`

`POST /api/analyze` accepts a form upload named `file`, plus optional `runway_id`, `drone_id`, `drone_latitude`, `drone_longitude`, and `drone_altitude_m`.

For the frontend workflow, use `POST /api/analyze-frame` for images and `POST /api/analyze` for videos. The backend then runs these tasks:

1. YOLO inference on the image to decide lamp states and global PAPI state.
2. Angle calculation from the submitted drone metadata and selected runway coordinates.

The endpoint returns results immediately and stores a lightweight database log with result metadata, not the uploaded image/video bytes. Uploaded originals are deleted after processing; annotated image and full labeled video exports stay in `storage/exports`.

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
Dockerfile          FastAPI container used by the root compose file
```

## Angle Calculation

When uploaded media contains GPS latitude, longitude, and altitude metadata, or when those values are sent manually in the form data, the backend calculates the drone elevation angle using the same formula from the data-analysis notebook:

```text
distance = haversine(drone_lat, drone_lon, light_lat, light_lon)
angle = degrees(atan2(drone_alt - light_alt, distance))
```

If metadata is missing, the API returns `angle_available: false` instead of inventing a degree. Since frontend-generated frame images may not preserve original drone EXIF/telemetry, the frontend should send `drone_latitude`, `drone_longitude`, and `drone_altitude_m` with each frame whenever possible.

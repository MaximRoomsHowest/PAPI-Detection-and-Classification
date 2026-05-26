# PAPI Backend

Local-only FastAPI backend trial for immediate PAPI image/video analysis with database-backed result logs.

## Setup

```bash
cd Backend_main
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d
python -m uvicorn app.main:app
```

The API will run at `http://127.0.0.1:8000`.

## Model

The local model should be available at:

```text
models/best.pt
```

This file is intentionally ignored by Git. It can be copied from the `data_analysis` branch:

```bash
git show origin/data_analysis:data/runs/detect/train-2/weights/best.pt > models/best.pt
```

## Endpoints

- `GET /health`
- `POST /api/analyze`
- `POST /api/analyze-frame`
- `GET /api/logs`
- `GET /api/logs/{id}`
- `GET /api/runways`

`POST /api/analyze` accepts a form upload named `file`, plus optional `runway_id`, `drone_id`, `drone_latitude`, `drone_longitude`, and `drone_altitude_m`.

For the frontend video workflow, use `POST /api/analyze-frame`: the frontend splits video into image frames and sends each frame with drone metadata. The backend then runs exactly two tasks for that frame:

1. YOLO inference on the image to decide lamp states and global PAPI state.
2. Angle calculation from the submitted drone metadata and selected runway coordinates.

The endpoint returns both results immediately and stores a lightweight database log with result metadata, not the uploaded image/video bytes. Uploaded originals are deleted after processing; annotated exports stay in `storage/exports`.

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
```

## Angle Calculation

When uploaded media contains GPS latitude, longitude, and altitude metadata, or when those values are sent manually in the form data, the backend calculates the drone elevation angle using the same formula from the data-analysis notebook:

```text
distance = haversine(drone_lat, drone_lon, light_lat, light_lon)
angle = degrees(atan2(drone_alt - light_alt, distance))
```

If metadata is missing, the API returns `angle_available: false` instead of inventing a degree. Since frontend-generated frame images may not preserve original drone EXIF/telemetry, the frontend should send `drone_latitude`, `drone_longitude`, and `drone_altitude_m` with each frame whenever possible.

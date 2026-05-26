# PAPI Backend

Local-only FastAPI backend trial for immediate PAPI image/video analysis with database-backed result logs.

## Setup

```powershell
cd apps/backend
..\..\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
docker compose up -d
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The API will run at `http://127.0.0.1:8000`.

## Model

The local model should be available at:

```text
../../models/serving/best.pt
```

This file is intentionally ignored by Git. For local smoke testing, copy a local base weight:

```powershell
Copy-Item ..\..\models\base\yolo26n.pt ..\..\models\serving\best.pt -Force
```

For project-quality demos, replace `models/serving/best.pt` with the intended trained PAPI checkpoint.

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

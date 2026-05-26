# Local FastAPI Backend Trial Plan

## Purpose

This folder contains the local FastAPI backend for the PAPI Detection and Classification project. It now serves the React frontend's Backend API mode while still being runnable on its own.

The backend lets a user upload an image or video, run the trained PAPI YOLO model immediately, store an anonymous result log, export annotated media, and calculate the drone elevation angle when GPS/altitude metadata is available.

## What Is Implemented

- FastAPI API with optional `PAPI_API_KEY` protection for hosted/local shared use.
- Image/frame upload through `POST /api/analyze-frame`; legacy image/video upload remains available through `POST /api/analyze`.
- Immediate inference response from `POST /api/analyze`; no job polling is used for v1.
- PostgreSQL result logs that store metadata/results, not uploaded image/video bytes.
- Seeded PAPI runway coordinates for `papi_06` and `papi_24`.
- YOLO `.pt` inference using `../models/serving/best.pt` by default.
- Lamp-level result output: each detected lamp is reported as `white`, `red`, or `unknown`.
- Global PAPI state output: `far_too_high`, `too_high`, `correct_glidepath`, `too_low`, `far_too_low`, or `unknown`.
- Annotated image/video export support.
- Drone elevation angle calculation using the data-analysis notebook formula:

```text
distance = haversine(drone_lat, drone_lon, light_lat, light_lon)
angle = degrees(atan2(drone_alt - light_alt, distance))
```

If GPS/altitude metadata is missing, the backend returns `angle_available: false` instead of guessing an exact angle.

## Folder Contents

```text
Backend_main/
  app/
    main.py                 FastAPI app entrypoint
    config.py               Environment/settings loading
    database.py             SQLAlchemy engine/session setup
    api/routes.py           API endpoints
    models/
      analysis_log.py       SQLAlchemy analysis log entity
    repositories/
      analysis_logs.py      Database read/write logic for result logs
    services/
      angle.py              EXIF metadata + drone angle calculation
      inference.py          YOLO/OpenCV media analysis
      media.py              Upload and media-type helpers
      runways.py            Seeded PAPI runway coordinates
      state.py              Lamp and global-state logic
    validation/
      analyze.py            Request validation helpers
      schemas.py            API response/request models
  storage/
    uploads/                Uploaded files, ignored by Git
    exports/                Annotated output files, ignored by Git
    tmp/                    Temporary processing files, ignored by Git
  tests/                    Unit tests
  docker-compose.yml        Local PostgreSQL service for logs
  requirements.txt          Python dependencies
  .env.example              Example local environment config
../models/
  serving/best.pt           Local backend model, ignored by Git
```

## API Endpoints

- `GET /health`
- `POST /api/analyze`
- `POST /api/analyze-frame`
- `GET /api/logs`
- `GET /api/logs/{id}`
- `GET /api/runways`

`POST /api/analyze-frame` is the expected frontend workflow for split video frames. It expects form data:

- `file`: image frame upload
- `runway_id`: optional, defaults to `papi_06`
- `drone_id`: optional
- `drone_latitude`, `drone_longitude`, `drone_altitude_m`: optional manual drone metadata for angle calculation

Backend work per received frame:

- Run inference on the image and decide each PAPI lamp state plus global state.
- Calculate drone elevation angle from submitted metadata and seeded runway coordinates.
- Return the result immediately and save only a lightweight DB log.

## How To Run Locally

```bash
cd Backend_main
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d
python -m uvicorn app.main:app
```

The API runs at:

```text
http://127.0.0.1:8000
```

Interactive docs:

```text
http://127.0.0.1:8000/docs
```

## How To Test

```bash
cd Backend_main
source .venv/bin/activate
pytest
```

Current unit test coverage includes:

- PAPI angle calculation
- Media type validation
- Lamp sorting and global-state mapping

## Important Notes

- This is local-first work. Nothing has been pushed.
- The frontend is connected through Backend API mode using `VITE_PAPI_API_URL`.
- `../models/serving/best.pt` is intentionally ignored by Git.
- Uploaded originals are used for processing and deleted after analysis.
- Annotated exports, temp files, `.env`, and virtual environments are ignored by Git.
- Docker Desktop must be running before `docker compose up -d` will work.
- The exact drone angle is only calculated when GPS/altitude metadata is available in the uploaded media or provided manually in the request. For frontend-split frames, metadata should normally be sent as request form fields.
- Transition/yellow-orange lamp detection is reserved for later unless the model gains a transition class.

## Suggested Next Steps

- Start PostgreSQL with Docker and run the FastAPI app.
- Test `/api/analyze-frame` and `/api/analyze` with real media.
- Verify annotated exports visually.
- Keep frontend Backend API mode aligned with backend response schemas.
- Later, decide if large video files need a separate background-job endpoint.

# Local FastAPI Backend Trial Plan

## Purpose

This folder contains the FastAPI backend for the PAPI Detection and Classification project. On the `integration/full-flow` branch it is connected to the React UI through local image and video analysis endpoints.

The backend lets a user upload an image frame, run the trained PAPI YOLO model immediately, store an anonymous result log, export annotated media, and calculate the drone elevation angle when GPS/altitude metadata is submitted by the frontend.

## What Is Implemented

- Public FastAPI API with no login/authentication.
- Image/frame upload through `POST /api/analyze-frame`; video upload uses `POST /api/analyze` so the backend can return a full labeled video export.
- Immediate inference response from `POST /api/analyze`; no job polling is used for v1.
- PostgreSQL result logs that store metadata/results, not uploaded image/video bytes.
- Seeded PAPI runway coordinates for `papi_06` and `papi_24`.
- YOLO `.pt` inference using the trained model from `data_analysis`.
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
backend/
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
  models/
    best.pt                 Local trained YOLO model, ignored by Git
  storage/
    uploads/                Uploaded files, ignored by Git
    exports/                Annotated output files, ignored by Git
    tmp/                    Temporary processing files, ignored by Git
  tests/                    Unit tests
  Dockerfile                FastAPI container used by the root compose file
  requirements.txt          Python dependencies
  .env.example              Example local environment config
```

## API Endpoints

- `GET /health`
- `POST /api/analyze`
- `POST /api/analyze-frame`
- `GET /api/logs`
- `GET /api/logs/{id}`
- `GET /api/runways`

`POST /api/analyze-frame` is the expected frontend workflow for images. `POST /api/analyze` is the expected frontend workflow for videos. Both expect form data:

- `file`: image frame upload
- `runway_id`: optional, defaults to `papi_06`
- `drone_id`: optional
- `drone_latitude`, `drone_longitude`, `drone_altitude_m`: optional manual drone metadata for angle calculation

Backend work per received image or video:

- Run inference on the image and decide each PAPI lamp state plus global state.
- Calculate drone elevation angle from submitted metadata and seeded runway coordinates.
- Return the result immediately and save only a lightweight DB log. Video responses include an annotated video export URL.

## How To Run Locally

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d postgres
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
cd backend
source .venv/bin/activate
python -m pytest
```

Current unit test coverage includes:

- PAPI angle calculation
- Media type validation
- Lamp sorting and global-state mapping

## Important Notes

- This is local-only work. Nothing has been pushed.
- The frontend is connected locally through `POST /api/analyze-frame` for images and `POST /api/analyze` for videos.
- `models/best.pt` is intentionally ignored by Git.
- Uploaded originals are used for processing and deleted after analysis.
- Annotated exports, temp files, `.env`, and virtual environments are ignored by Git.
- Docker Desktop must be running before `docker compose up -d` will work.
- The exact drone angle is only calculated when GPS/altitude metadata is available in the uploaded media or provided manually in the request. For frontend-split frames, metadata should normally be sent as request form fields.
- Transition/yellow-orange lamp detection is reserved for later unless the model gains a transition class.

## Suggested Next Steps

- Start PostgreSQL with Docker and run the FastAPI app.
- Test `/api/analyze` with a real image and video.
- Verify annotated exports visually.
- Keep improving frontend frame sampling and aggregation.
- Later, decide if large server-side video files need a separate background-job endpoint.

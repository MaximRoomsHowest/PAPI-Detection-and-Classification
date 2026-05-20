# Local FastAPI Backend Trial Plan

## Purpose

This folder contains a local-only FastAPI backend prototype for the PAPI Detection and Classification project. It is separate from the frontend work and is meant to prove the backend flow before connecting it to the React UI.

The backend lets a user upload an image or video, run the trained PAPI YOLO model, store an anonymous analysis log, export annotated media, and calculate the drone elevation angle when GPS/altitude metadata is available.

## What Is Implemented

- Public FastAPI API with no login/authentication.
- Image and video upload through one analysis endpoint.
- Background processing job flow for uploaded media.
- PostgreSQL database models for analysis jobs and results.
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
Backend_main/
  app/
    main.py                 FastAPI app entrypoint
    config.py               Environment/settings loading
    database.py             SQLAlchemy engine/session setup
    models.py               Database tables
    schemas.py              API response/request models
    api/routes.py           API endpoints
    services/
      angle.py              EXIF metadata + drone angle calculation
      inference.py          YOLO/OpenCV media analysis
      media.py              Upload and media-type helpers
      processor.py          Background job processor
      runways.py            Seeded PAPI runway coordinates
      state.py              Lamp and global-state logic
  models/
    best.pt                 Local trained YOLO model, ignored by Git
  storage/
    uploads/                Uploaded files, ignored by Git
    exports/                Annotated output files, ignored by Git
    tmp/                    Temporary processing files, ignored by Git
  tests/                    Unit tests
  docker-compose.yml        Local PostgreSQL service
  requirements.txt          Python dependencies
  .env.example              Example local environment config
```

## API Endpoints

- `GET /health`
- `POST /api/analyze`
- `GET /api/analyze/{job_id}`
- `GET /api/logs`
- `GET /api/logs/{job_id}`
- `GET /api/runways`

`POST /api/analyze` expects form data:

- `file`: image or video upload
- `runway_id`: optional, defaults to `papi_06`
- `drone_id`: optional
- `notes`: optional

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

- This is local-only work. Nothing has been pushed.
- The frontend is not connected yet.
- `models/best.pt` is intentionally ignored by Git.
- Uploaded files, exports, temp files, `.env`, and virtual environments are ignored by Git.
- Docker Desktop must be running before `docker compose up -d` will work.
- The exact drone angle is only calculated when GPS/altitude metadata is available.
- Transition/yellow-orange lamp detection is reserved for later unless the model gains a transition class.

## Suggested Next Steps

- Start PostgreSQL with Docker and run the FastAPI app.
- Test `/api/analyze` with a real image and video.
- Verify annotated exports visually.
- Add frontend polling once the backend result shape is confirmed.
- Later, decide whether to keep PostgreSQL or temporarily support SQLite for easier teammate setup.

# Local FastAPI Backend Trial Plan

> **Historical planning note.** This file is the original backend trial plan, kept for
> provenance. Parts below (folder layout, endpoint list, the v1.0 framing) predate later
> refactors — for the authoritative current backend reference, see
> [`apps/backend/README.md`](./README.md).

## Purpose

This folder contains the local FastAPI backend for the PAPI Detection and Classification project. It now serves the React frontend's Backend API mode while still being runnable on its own.

The backend lets a user upload an image or video, run the trained PAPI YOLO model immediately, store an anonymous result log, export annotated media, and calculate the drone elevation angle when GPS/altitude metadata is available.

## What Is Implemented

- FastAPI API with optional `PAPI_API_KEY` protection for hosted/local shared use.
- Image/frame upload through `POST /api/analyze-frame`; legacy image/video upload remains available through `POST /api/analyze`.
- Immediate inference response from `POST /api/analyze`; no job polling is used for v1.
- PostgreSQL result logs that store metadata/results, not uploaded image/video bytes.
- Seeded PAPI runway coordinates for `papi_06` and `papi_24`.
- YOLO `.pt` inference using `../../models/serving/best.pt` by default.
- Lamp-level result output: each detected lamp is reported per frame as `white`, `red`, or `unknown` (the YOLO detector is two-class: 0=red, 1=white — see `app/services/state.py:normalize_detections`). A lamp's white↔red `transition` is recognised **temporally** — a colour switch across video frames of the same tracked lamp — by `detect_lamp_transitions`, NOT as a per-frame class. (The geometric set-angle transition band in `packages/papi/src/papi/lamp_state.py` is used only by the offline dataset-labelling pipeline, never at runtime.)
- Global PAPI state output: `far_too_high`, `too_high`, `correct_glidepath`, `too_low`, `far_too_low`, or `unknown`.
- Annotated image/video export support.
- Drone elevation angle calculation using a WGS-84 LLA→ECEF→ENU transform. (The early
  haversine approximation was replaced; `haversine` is now retained only for a
  horizontal-distance display/cross-check — see `apps/backend/README.md`.)

```text
elevation = degrees(atan2(Up, hypot(East, North)))
```

If GPS/altitude metadata is missing, the backend returns `angle_available: false` instead of guessing an exact angle.

## Folder Contents

```text
apps/backend/
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
  storage/                  Runtime-created, ignored by Git
    uploads/                Uploaded files
    exports/                Annotated output files
    tmp/                    Temporary processing files
  tests/                    Unit tests
  Dockerfile                Container image for the backend
  pytest.ini                Pytest configuration
  requirements.txt          Python dependencies
  .env.example              Example local environment config
../../models/
  serving/best.pt           Backend runtime model (tracked)
  base/                     Base weights (tracked)
  runs/                     Training run outputs (tracked)
```

## API Endpoints

- `GET /health`
- `POST /api/analyze`
- `POST /api/analyze-frame`
- `POST /api/analyze-frames`
- `GET /api/logs`
- `GET /api/logs/{id}`
- `GET /api/runways`

`POST /api/analyze-frame` is the expected frontend workflow for split video frames. It expects form data:

- `file`: image frame upload
- `runway_id`: optional, defaults to `papi_24`
- `drone_id`: optional
- `drone_latitude`, `drone_longitude`, `drone_altitude_m`: optional manual drone metadata for angle calculation

`POST /api/analyze-frames` is the batch variant powering the frontend folder-upload workflow. It accepts the same drone-metadata fields plus a multipart upload named `files` (plural) containing multiple image files. The response is a `FrameBatchPayload` with `frame_count`, total `processing_ms`, and `results: list[AnalysisPayload]` mirroring each `analyze-frame` call.

Backend work per received frame:

- Run inference on the image and decide each PAPI lamp state plus global state.
- Calculate drone elevation angle from submitted metadata and seeded runway coordinates.
- Return the result immediately and save only a lightweight DB log.

## How To Run Locally

```bash
cd apps/backend
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
cd apps/backend
source .venv/bin/activate
pytest
```

Current unit test coverage includes:

- PAPI angle calculation
- Media type validation
- Lamp sorting and global-state mapping

## Important Notes

- This is the v1.0-released backend. Source is in Git with the `v1.0` tag.
- The frontend is connected through Backend API mode using `VITE_PAPI_API_URL`.
- `../../models/serving/best.pt` is intentionally ignored by Git.
- Uploaded originals are used for processing and deleted after analysis.
- Annotated exports, temp files, `.env`, and virtual environments are ignored by Git.
- Docker Desktop must be running before `docker compose up -d` will work.
- The exact drone angle is only calculated when GPS/altitude metadata is available in the uploaded media or provided manually in the request. For frontend-split frames, metadata should normally be sent as request form fields.
- Transition recognition is **temporal**, not a third detector class: `services/state.py:detect_lamp_transitions` reports a white↔red switch when a ByteTrack-tracked lamp changes colour between video frames (tolerating a small `TRANSITION_MAX_FRAME_GAP` so a brief dropout doesn't drop a real switch). It is fully independent of runway/angle — the elevation angle is only *attached* to each event as an annotation. The geometric set-angle band (`packages/papi/src/papi/lamp_state.py`) is an offline dataset-labelling tool only. NOTE: there is no per-frame yellow/orange lamp classifier at runtime, so a single still image shows lamps as red/white/unknown and per-lamp transitions are reported across video frames.

## Suggested Next Steps

- Start PostgreSQL with Docker and run the FastAPI app.
- Test `/api/analyze-frame` and `/api/analyze` with real media.
- Verify annotated exports visually.
- Keep frontend Backend API mode aligned with backend response schemas.
- Later, decide if large video files need a separate background-job endpoint.

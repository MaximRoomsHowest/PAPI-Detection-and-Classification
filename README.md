# PAPI Detection and Classification

Integrated local full-flow branch for the PAPI project.

## Project Layout

```text
frontend/   React/Vite interface for upload, frame extraction, metadata input, and result display
backend/    FastAPI API, YOLO inference service, angle calculation, and PostgreSQL log storage
data/       Data-analysis notebooks, datasets, and trained YOLO weights
```

The frontend sends images to `POST /api/analyze-frame` and videos to `POST /api/analyze`. The backend runs YOLO inference, calculates the angle when metadata is present, stores a lightweight log, and returns an annotated image or full labeled video export.

## Run Everything Locally

Docker Desktop must be running.

```bash
docker compose up --build
```

Local URLs:

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- Backend docs: `http://localhost:8000/docs`
- PostgreSQL: `localhost:5434`

The root compose file mounts the trained model from:

```text
data/runs/detect/train-3/weights/best.pt
```

## Useful Local Commands

```bash
cd backend
source .venv/bin/activate
python -m pytest
```

```bash
cd frontend
npm install
npm run build
```

This branch is local integration work. Do not push until the team is ready to review it.

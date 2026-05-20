# PAPI Backend

Local-only FastAPI backend trial for PAPI image/video analysis.

## Setup

```bash
cd backend
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
backend/models/best.pt
```

This file is intentionally ignored by Git. It can be copied from the `data_analysis` branch:

```bash
git show origin/data_analysis:data/runs/detect/train-2/weights/best.pt > backend/models/best.pt
```

## Endpoints

- `GET /health`
- `POST /api/analyze`
- `GET /api/analyze/{job_id}`
- `GET /api/logs`
- `GET /api/logs/{id}`
- `GET /api/runways`

`POST /api/analyze` accepts a form upload named `file`, plus optional `runway_id`, `drone_id`, and `notes`.

## Angle Calculation

When uploaded media contains GPS latitude, longitude, and altitude metadata, the backend calculates the drone elevation angle using the same formula from the data-analysis notebook:

```text
distance = haversine(drone_lat, drone_lon, light_lat, light_lon)
angle = degrees(atan2(drone_alt - light_alt, distance))
```

If metadata is missing, the API returns `angle_available: false` instead of inventing a degree.

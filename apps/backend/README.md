# PAPI Backend

Local-only FastAPI backend trial for immediate PAPI image/video analysis with database-backed result logs.

## Setup

For full-stack local development use the **root** Compose stack (`compose.yaml`),
which brings up Postgres + this backend + the React frontend together. From
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
..\..\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
copy .env.example .env
..\..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API will run at `http://127.0.0.1:8000`. Interactive docs at
`http://127.0.0.1:8000/docs`.

## Authentication

The backend supports provider auth through `PAPI_AUTH_MODE`: `open`, `api_key`,
`local`, `supabase`, and `local_supabase` (`auto` preserves the legacy local
behavior). For the client local-machine handoff, choose `local` for one backend
admin account or `supabase` for Supabase-managed users. The legacy
`PAPI_API_KEY` remains supported as `X-API-Key` and can be kept as a
break-glass fallback.

Setup details and credential-generation commands live in
[`../../docs/authentication.md`](../../docs/authentication.md). That guide also
contains the demo-only local account used in the user manual; rotate it before
any real deployment.

## Models

Selectable inference models are owned by the backend registry:

```text
../../models/serving/models.json
```

`GET /api/models` returns the configured choices, whether each weight exists,
whether it is loaded, and why a choice is disabled. `GET /api/model` stays
backward-compatible and returns the default model unless `model_id` is supplied.

The default model still lives at:

```text
../../models/serving/best.pt
```

This file is tracked in Git via Git LFS-like whitelisted patterns in the
root `.gitignore` (see lines 67-72 there). For local smoke testing without
a trained model, copy a base weight into the serving slot:

```powershell
Copy-Item ..\..\models\base\yolo26s.pt ..\..\models\serving\best.pt -Force
```

For project-quality demos, replace `models/serving/best.pt` with the intended
trained PAPI checkpoint and keep `models/serving/models.json` aligned. The
registered `transition` classifier points at an ignored `data/runs/...` artifact;
if that file is absent, the API reports it as unavailable and the Live Demo
disables it instead of failing startup.

## Endpoints

- `GET /health` · `GET /health/ready` (readiness probe)
- `GET /api/auth/config` · `GET /api/auth/me` · `POST /api/auth/login` · `POST /api/auth/logout`
- `GET /media/{file_path}` (annotated artifacts)
- `POST /api/analyze`
- `POST /api/analyze-frame`
- `POST /api/analyze-frames`
- `POST /api/analyze-sequence`
- `GET /api/logs` · `GET /api/logs/export.csv` · `GET /api/logs/{id}`
- `GET /api/stats`
- `GET /api/runways` · `GET /api/model` · `GET /api/models` · `GET /api/system`

`POST /api/analyze` accepts a form upload named `file`, plus optional `runway_id`, `model_id`, `drone_id`, `drone_latitude`, `drone_longitude`, and `drone_altitude_m`.

All analyze endpoints accept optional `model_id`. Unknown ids return 400. Missing
selected weights fail cleanly for direct API callers; unavailable registry entries
are disabled by the frontend. Selecting a `transition` role model defaults to
learned transition events, while detector models default to temporal tracking.
The older `transition_method` field is still accepted for compatibility.

`POST /api/analyze-frame` is the single-image endpoint the frontend uses for an image upload (`Upload media` with an image). It accepts one image plus the same optional drone metadata and runs exactly two tasks for that frame:

1. YOLO inference on the image to decide lamp states and global PAPI state.
2. Angle calculation from the submitted drone metadata and selected runway coordinates.

(A **video** upload instead goes whole to `POST /api/analyze`, where the backend decodes and tracks its frames — see above.)

`POST /api/analyze-frames` is the batch variant: accepts a multipart upload named `files` (plural) with multiple image files plus the same optional drone metadata. The backend processes each image **independently** with the same per-frame logic and returns a single `FrameBatchPayload` aggregating per-frame results plus total processing time.

`POST /api/analyze-sequence` is the **folder-to-video** variant and powers the frontend folder-upload workflow. It also accepts a multipart upload named `files` (plural) plus the same optional drone metadata, but instead of treating the images as independent frames it treats them as **consecutive frames of a single clip**: the images are ordered by filename, fed through the same ByteTrack-tracked pipeline as a real video (per-lamp identity carried across frames, temporal red↔white transitions), and the response is a single `AnalysisPayload` with one aggregated verdict and one annotated **WebM video** artifact. Playback speed / transition frame-gap timing is set by `PAPI_SEQUENCE_FPS` (default 4 fps); it does not affect detection. The viewing angle is read once from the first image (its EXIF, or the request's drone telemetry), mirroring the one-angle-per-video model. Both `/api/analyze-frames` and `/api/analyze-sequence` are bounded by `PAPI_MAX_BATCH_FRAMES` (default 200) frames per request.

The single-frame endpoints return their results immediately and store a lightweight database log with result metadata, not the uploaded image/video bytes. Uploaded originals are deleted after processing; annotated exports stay in `storage/exports`.

All HTTP responses include rate-limit headers when `PAPI_RATE_LIMIT_ENABLED`
is true. The default buckets are broad for dashboard/API traffic
(`PAPI_RATE_LIMIT_PER_MINUTE=600`), stricter for login attempts
(`PAPI_AUTH_RATE_LIMIT_PER_MINUTE=20`), and stricter for expensive
`/api/analyze*` inference requests (`PAPI_ANALYZE_RATE_LIMIT_PER_MINUTE=60`).
Exceeded buckets return a JSON `429` with `Retry-After`.

## Structure

```text
app/
  api/                       FastAPI HTTP layer
    routes.py                Public import surface; assembles the sub-routers + require_api_key
    routers/                 Endpoints split by concern:
      auth.py                  auth config, login, current user, logout
      analyze.py               analyze / analyze-frame / analyze-frames / analyze-sequence
      logs.py                  logs list, CSV export, detail
      stats.py                 aggregate stats
      meta.py                  runways, model info, system info
  models/                    SQLAlchemy database entities
  repositories/              Database read/write logic
  services/                  Media, angle, runway, and state logic
    auth.py                  provider-based operator auth
    inference/               Inference package:
      service.py               InferenceService facade (load, image/video/sequence)
      aggregation.py           per-lamp video verdict by track identity
      overlay.py               annotated-frame drawing
      video_writer.py          codec policy for the annotated video
      cv2_loader.py            lazy OpenCV import
  validation/                Pydantic schemas and request validation helpers
  config.py                  Environment/settings loading
  database.py                Database engine/session setup
  main.py                    FastAPI app entrypoint
../../models/
  serving/best.pt            Ignored local backend model loaded by default
```

## Angle Calculation

When uploaded media contains GPS latitude, longitude, and altitude metadata, or when those values are sent manually in the form data, the backend calculates the drone elevation angle using the **client's** geometry method (`app/services/angle.py`): both the drone and the PAPI are converted from WGS-84 LLA → ECEF → ENU (a local East-North-Up tangent frame at the PAPI), and the elevation angle is

```text
horizontal = sqrt(East**2 + North**2)
angle      = degrees(atan2(Up, horizontal))
```

The primary `elevation_angle_deg` is taken from the **PAPI midpoint** (centroid of the lamp row); `per_light_angles` returns one angle per lamp (each lamp as its own ENU origin) for the per-lamp charts. This replaces the earlier haversine + raw-altitude-subtraction approximation; at the 300-1000 m baselines in this dataset the two agree to ~0.01° internally, and the ENU result was validated to ~0.02° against the client's own tool. `haversine()` is retained only for horizontal-distance display / cross-checks.

For accuracy, GPS extraction prefers the RTK-corrected DJI XMP pose (`drone-dji:AbsoluteAltitude`, ellipsoidal height) over the GPS/baro-blended EXIF `GPSAltitude`, whose 1-15 m non-RTK vertical error is enough to drag the computed angle out of the true 2.5-4° band.

If metadata is missing, the API returns `angle_available: false` instead of inventing a degree. Since frontend-generated frame images may not preserve original drone EXIF/telemetry, the frontend should send `drone_latitude`, `drone_longitude`, and `drone_altitude_m` with each frame whenever possible.

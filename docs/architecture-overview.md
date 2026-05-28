# PAPI Vision — Technical Architecture Overview

For graders, reviewers, and new contributors. Explains how the
pieces fit together and why specific design choices were made.

> **Need to install or run the system?** See
> [installation-manual.md](installation-manual.md). For end-user
> usage, see [user-manual.md](user-manual.md).

## 1. System diagram

```
                          DJI Matrice 4E drone (data capture)
                                   │ JPGs + EXIF + DJI XMP
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│  OFFLINE  (workflows/scripts/pipeline.py + notebooks)            │
│                                                                  │
│  extract → calibrate → autolabel → sample → export → train       │
│                                                                  │
│  Outputs: configs/projection.yaml, data/labels/auto/,            │
│           data/interim/lamp_state.csv, CVAT bundle,              │
│           models/serving/best.pt                                 │
└──────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼ (trained weights)
┌──────────────────────────────────────────────────────────────────┐
│  ONLINE  (Docker compose: postgres + backend + frontend)         │
│                                                                  │
│   Browser  ── HTTPS ──►  Nginx (apps/frontend, port 8080)        │
│      │                         │                                 │
│      │                         ▼                                 │
│      │              Static React/Vite bundle                     │
│      │                                                           │
│      └── fetch /api/* ──►  FastAPI (apps/backend, port 8000)     │
│                                  │       │                       │
│                                  ▼       ▼                       │
│                          YOLO model    Postgres                  │
│                  (models/serving/best.pt)  ▲                     │
│                                            │                     │
│                                  analysis_logs (one row/request) │
└──────────────────────────────────────────────────────────────────┘
```

## 2. Repository layout

```
apps/
  backend/           FastAPI service, SQLAlchemy ORM, ultralytics
                     YOLO inference, OpenCV media handling
  frontend/         Vite/React SPA, Plotly charts, jsPDF export
packages/
  papi/             Reusable ML/data library — pure Python, no I/O,
    src/papi/         no FastAPI / SQLAlchemy dependency
    tests/          15 pytest tests, idempotent
workflows/
  scripts/          Runnable CLI entry points for the data pipeline
  notebooks/        8 Jupyter notebooks (training + evaluation)
configs/
  papi_edny.yaml    PAPI geometry + camera intrinsics for EDNY
  projection.yaml   Calibrated DJI gimbal Euler convention (generated)
  split.yaml        Flight-level train/val/test split
data/                Tracked READMEs + .gitkeep placeholders;
                     raw data archived externally
docs/                Label spec, pipeline doc, user manual,
                     installation manual, this file
models/              Tracked YOLO weights (base, serving, runs/)
test_videos/         3 small MP4 fixtures for upload smoke tests
.github/workflows/   CI workflow (Python + Frontend + Docker)
docker-compose.yml   Root: postgres + backend + frontend
pyproject.toml       Editable install for the papi package
```

## 3. Tech stack rationale

| Layer | Choice | Why |
| --- | --- | --- |
| Backend framework | **FastAPI 0.115** | Async first-class, Pydantic v2 schemas, OpenAPI docs free |
| ORM | **SQLAlchemy 2.0 (typed)** | Postgres native UUID + JSON support; mature |
| Database | **Postgres 16** | Reliable, transactional, free; the team has no NoSQL data shape |
| ML library | **ultralytics 8.3 (YOLO)** | De-facto standard for one-shot detection; INT8 ONNX path |
| Frontend | **React 19 + Vite 8** | Component model + fast dev loop; team familiarity |
| Charts | **Plotly (lazy-loaded)** | Interactive, accessible, deep matplotlib parity |
| Routing | **React Router 6 (v7 future flags)** | Stable, forward-compat |
| Reverse proxy | **Nginx (unprivileged)** | Battle-tested, small image, supports SPA fallback |
| Geodesy | **pymap3d** | Pure-Python WGS84; no proj/gdal headache |

## 4. Data flow per request

### POST `/api/analyze-frame` (single image)

```
1. Browser ──multipart upload──► FastAPI route handler
2. Validate metadata, save upload bytes to /storage/uploads/
3. cv2.imread(upload)
4. Compute per-lamp elevation angles from drone GPS + runway config
5. inference_service.model.predict(frame, conf=0.4)
   → list[Detection] with class_id (0=red, 1=white) + bbox + confidence
6. normalize_detections(detections, per_light_angles=angle.per_light_angles)
   → list[LampResult]; per-lamp state promoted to "transition" when
     |elevation - set_angle| <= 0.10°  (audit B-CRIT-1)
7. global_state_from_lamps(lamps) → "transition" / "4W" / "2W2R" / etc.
8. _draw_overlay(frame, lamps, ...) → annotated JPG at /storage/exports/
9. AnalysisLogRepository.create_from_payload(payload) → row in
   analysis_logs (Postgres)
10. Delete the upload, return AnalysisPayload as JSON
```

The same shape applies to `/api/analyze` (image or video — branches
internally on file extension) and `/api/analyze-frames` (a folder
batch — loops the single-image path).

## 5. Key design decisions

### 5.1 Two classes, transition inferred post-hoc

The YOLO model has only two output classes: `papi_light_red` (0) and
`papi_light_white` (1). The third state the client requested —
`transition` — is not a learned class. Instead, the backend
recomputes it geometrically at response time:

```
elevation_deg = angle(camera, lamp)
if |elevation_deg - set_angle_deg| <= transition_half_width_deg:
    state = "transition"
```

This pushes the boundary decision from the ML model (where labelled
transition data is scarce and the boundary is a near-degenerate
class) to a deterministic geometric computation (where the ground
truth is exact). The trade-off: the system needs valid drone GPS +
altitude metadata to emit transition state. When that's absent the
fall-back is `white` / `red` from the detector.

Implementation: `apps/backend/app/services/state.py:normalize_detections`
consumes the same algorithm that lives in
`packages/papi/src/papi/lamp_state.py:compute_lamp_state`
(used by the offline pipeline). One source of truth.

### 5.2 Geometry-driven auto-labelling

Manually labelling 4,058 frames was infeasible. The pipeline
auto-labels by projecting each lamp's surveyed WGS84 coordinate
through the calibrated DJI gimbal Euler convention into image
pixels — a bounding box is drawn around the projected centre. Only
the 2,984-frame verification sample (frames near boundaries,
RTK-uncertain positions, or zoom-camera) was manually corrected in
CVAT.

The calibration step (`workflows/scripts/pipeline.py calibrate`)
brute-forces 384 candidate Euler conventions against ~48 LRF
bore-sight frames and picks the one with the lowest median pixel
residual. Result for EDNY: median 6.05 px, max 21.0 px (over 48
frames across 16 flights).

See `docs/pipeline.md` for the detailed calibration result and
`packages/papi/src/papi/projection.py` for the implementation.

### 5.3 Dual-runway resolution

The EDNY dataset contains flights targeting **both** runways at the
single physical strip (06 on night flights, 24 on day flights). The
project hub originally documented a runway-06-only assumption; the
pipeline correctly auto-resolves which PAPI each frame is observing
via `packages/papi/src/papi/geometry.py:resolve_papi_for_frame`.

`configs/papi_edny.yaml` carries surveyed coordinates for both
runways under `runways.06.papi` and `runways.24.papi`.

### 5.4 Per-lamp temporal tracking (for video / sequence)

Across consecutive frames, the per-lamp track ID is assigned by:

1. **Projection-based assignment** when the camera is a calibrated
   WideCamera with valid airport config — solves the
   `det × projected_lamp` cost matrix via Hungarian assignment
   (`scipy.optimize.linear_sum_assignment`).
2. **Left-to-right fallback** otherwise — orders detections by
   pixel-x and assigns lamp 1..N in order.

Transitions are then extracted by walking each track's per-frame
states and emitting a row whenever a stable lamp flips between
`white` and `red` on *consecutive* frames (no transitions across
missing-label gaps).

Implementation: `packages/papi/src/papi/tracking.py`.

### 5.5 Result persistence — metadata only, not media

Every analysis writes one row to `analysis_logs` with the per-lamp
state, global state, confidence, processing time, runway, drone
ID, and the full result JSON. The uploaded image / video bytes are
**deleted** after processing — only the annotated artifact is
retained at `/storage/exports/`. This keeps the database small
and the privacy story simple.

The `/api/logs` endpoint (auth-gated) lets the team retrieve
recent results for analysis.

## 6. Frontend application structure

`apps/frontend/src/App.jsx` (currently a single large file —
modularisation deferred to a design pass) defines three routes:

| Route | Component | Purpose |
| --- | --- | --- |
| `/` | `IntroductionPage` | Hero, project context, airport map |
| `/live-demo` | `LiveDemoPage` | Three upload paths, scenario tabs, frame-stage + analysis panel |
| `/insights` | `InsightsPage` | PAPI state decoder bar chart, transition ribbon heatmap, PDF export |

Theme is driven by CSS custom properties on `html[data-theme]`.
Brand identity: Intersoft navy (`#00426e`), Poppins typography,
restrained palette.

API client lives in `src/lib/api.js` — three functions
(`analyzeMedia`, `analyzeFrame`, `analyzeFrames`) wrap `fetch`.

## 7. Deployment & operations

- **Containerised** via `docker-compose.yml`. Three services, one
  named network, two named volumes, three healthchecks, three
  restart policies (`unless-stopped`).
- **Logs**: JSON file with 10 MB × 5 file rotation per service.
- **Security floor**:
  - Both runtime containers run as non-root users (`papi`, `nginx`).
  - Postgres bound to `127.0.0.1` only; service-to-service access
    via the internal compose network.
  - `PAPI_ENV=production` makes `PAPI_API_KEY` mandatory at startup.
  - nginx ships baseline security headers (CSP, X-Frame-Options,
    Referrer-Policy, Permissions-Policy, X-Content-Type-Options).
- **CI**: GitHub Actions runs pytest + ruff + npm lint + npm build +
  Docker build on every push (`.github/workflows/ci.yml`).

## 8. Known scope limitations

| Item | Status | Where to look |
| --- | --- | --- |
| ZoomCamera auto-labelling | Skipped sprint 1 | `configs/papi_edny.yaml:55` (focal_px = null) |
| EDNY commissioned set-angles | FAA defaults used | `configs/papi_edny.yaml` (TODO comments) |
| Multi-airport generalisation | Out of scope for v1.0 | One YAML per airport; geometry library already supports it |
| Real-time inference (>10 fps) | ~2 fps on CPU | INT8 ONNX exists; GPU not configured |
| Edge-device deployment | Not yet measured | `docs/edge-benchmark.md` template ready for the team |

## 9. Sources of truth

- **Code structure**: this file + `README.md`
- **Labels and per-lamp state semantics**: `docs/label_spec.md`
- **Pipeline stages and their I/O**: `docs/pipeline.md`
- **Open questions and decisions**:
  [BigBrain project hub](../README.md) (`03-projects/intersoft-papi-detection`)
- **Known issues (audited 2026-05-27)**:
  [BigBrain audit](../README.md) (`03-projects/papi-codebase-audit-2026-05-27`)

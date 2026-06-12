# PAPI Lights Detection and Classification — Technical Architecture Overview

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
│  extract → calibrate → autolabel → sample → export              │
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
│   Browser  ── HTTP* ──►  Nginx (apps/frontend, port 8080)        │
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

\* Plain HTTP on localhost in the compose setup; TLS terminates at the Azure
Container Apps ingress in the cloud deployment.

## 2. Repository layout

```
apps/
  backend/           FastAPI service, SQLAlchemy ORM, ultralytics
                     YOLO inference, OpenCV media handling. HTTP layer
                     split into app/api/routers/ (analyze/logs/stats/meta);
                     inference engine in app/services/inference/
  frontend/         Vite/React SPA (route shell + pages/, LiveDemo state
                     via React context), Plotly charts, jsPDF export
packages/
  papi/             Reusable ML/data library — pure Python, no I/O,
    src/papi/         no FastAPI / SQLAlchemy dependency
    tests/          pytest suite, idempotent
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
compose.yaml         Root: postgres + backend + frontend
pyproject.toml       Editable install for the papi package
```

## 3. Tech stack rationale

| Layer | Choice | Why |
| --- | --- | --- |
| Backend framework | **FastAPI 0.115** | Async first-class, Pydantic v2 schemas, OpenAPI docs free |
| ORM | **SQLAlchemy 2.0 (typed)** | Postgres native UUID + JSON support; mature |
| Database | **Postgres 18** | Reliable, transactional, free; the team has no NoSQL data shape |
| ML library | **ultralytics 8.3 (YOLO)** | De-facto standard for one-shot detection; INT8 ONNX path |
| Frontend | **React 19 + Vite 8** | Component model + fast dev loop; team familiarity |
| Charts | **Plotly (lazy-loaded partial bundle)** | Re-evaluated 2026-06 against ECharts, Vega-Lite, Recharts and Observable Plot with built prototypes: alternatives save at most ~174 kB gz on an already lazy, cached chunk, but force rewriting all nine charts plus the `Plotly.toImage` PDF-export path. Kept Plotly (core + scatter/bar/heatmap/histogram only) |
| Routing | **React Router 6 (v7 future flags)** | Stable, forward-compat |
| Reverse proxy | **Nginx (unprivileged)** | Battle-tested, small image, supports SPA fallback |
| Geodesy | **pymap3d** | Pure-Python WGS84; no proj/gdal headache |

## 4. Data flow per request

### POST `/api/analyze-frame` (single image)

```
1. Browser ──multipart upload──► FastAPI route handler
2. Validate metadata, save upload bytes to /storage/uploads/
3. cv2.imread(upload)
4. Compute per-lamp + PAPI-midpoint elevation angles from drone GPS + runway config
   via a WGS-84 LLA->ECEF->ENU transform (client method; app/services/angle.py)
5. inference_service.model.predict(frame, conf=0.4)
   → list[Detection] with class_id (0=red, 1=white) + bbox + confidence
6. normalize_detections(detections) → list[LampResult]; each lamp's
   per-frame state is red / white / unknown / obscured only — a single
   image cannot show a "transition". (Temporal red↔white transitions are
   detected separately for video / sequence by state.detect_lamp_transitions
   over ByteTrack-tracked frames; see §5.1 and §5.4.)
7. global_state_from_lamps(lamps) → "4W" / "2W2R" / etc. (a white-count
   lookup over the four lamps; "transition" only when a lamp is already
   mid-transition, which a single frame never is)
8. _draw_overlay(frame, lamps, ...) → annotated JPG at /storage/exports/
9. AnalysisLogRepository.create_from_payload(payload) → row in
   analysis_logs (Postgres)
10. Delete the upload, return AnalysisPayload as JSON
```

The same shape applies to `/api/analyze` (image or video — branches
internally on file extension) and `/api/analyze-frames` (a folder
batch — loops the single-image path, one independent result per image).

`/api/analyze-sequence` (the folder→video feature) takes the same
multipart image list but treats the files as **consecutive frames of
one clip**: it orders them by filename and runs them through the same
ByteTrack-tracked core as a real video upload, so per-lamp identity
carries across frames and temporal red↔white transitions are detected.
The response is a single `AnalysisPayload` with one aggregated verdict
and one annotated WebM artifact; a synthetic FPS (`PAPI_SEQUENCE_FPS`,
default 4) drives playback/transition-gap timing, not detection. The
viewing angle is read once from the first image. Both the batch and
sequence endpoints are bounded by `PAPI_MAX_BATCH_FRAMES`.

The HTTP layer is split by concern under `apps/backend/app/api/`:
`routes.py` is the public import surface that assembles four
sub-routers in `app/api/routers/` — `analyze` (the four upload/inference
endpoints above), `logs` (list / CSV export / detail), `stats`
(aggregate stats), and `meta` (runways / model info / system info).
`/api/logs`, its CSV export, and `/api/stats` all accept the same six
optional filters (`runway_id`, `media_type`, `global_state`,
`created_after`, `min_confidence`, `model_id`), validated once in
`app/api/_filters.py`, so the History table, its export, and its
summary cards always describe the same slice.
The inference engine lives in the `app/services/inference/` package: a
`service.py` facade (`InferenceService`: model load, image / video /
sequence) over leaf modules `aggregation` (per-lamp video verdict by
track identity), `overlay` (annotated-frame drawing), `video_writer`
(the annotated-video codec policy) and `cv2_loader` (lazy OpenCV import).

## 5. Key design decisions

### 5.1 Two classes, transition inferred temporally

The YOLO model has only two output classes: `PAPI-Red` (0) and
`PAPI-White` (1) (named `papi_light_red` / `papi_light_white` in the
dataset / labelling taxonomy). The third state the client requested —
`transition` — is **not** a learned class, and it is **not** a per-frame
verdict at all: a single image can only show a lamp as red, white,
unknown, or obscured.

`apps/backend/app/services/state.py:normalize_detections` maps the
detector's per-frame boxes to those four states only. A `transition` is
instead a red↔white *change observed over time*:
`state.detect_lamp_transitions` walks each ByteTrack-tracked lamp across
consecutive frames (numbered 1..4 left-to-right via `lamp_index_by_track`)
and emits a transition event whenever a lamp flips between red and white
within `TRANSITION_MAX_FRAME_GAP` frames.

```
for each ByteTrack-tracked lamp:
    for consecutive observations (frame_a, state_a), (frame_b, state_b):
        if {state_a, state_b} == {"red", "white"}:
            emit TransitionEvent(lamp, frame_b, angle_at(frame_b))
```

The drone-metadata elevation angle does **not** decide a transition — it
only *annotates* each event (the viewing angle at the frame where the flip
was seen), so a per-frame telemetry track records the angle a lamp
actually switched at. This pushes the boundary decision off the ML model
(where labelled transition data is scarce and the boundary is a
near-degenerate class) and onto the temporal tracker, which only fires on
an observed colour flip. Consequently transitions exist only for video /
sequence uploads (§5.4); a still image never carries a transition state.

### 5.1a Elevation-angle method and transition-angle validation

The viewing angle that annotates each transition event (and drives the
per-lamp angle charts) is computed with the **client's** geometry, in
`apps/backend/app/services/angle.py`: both
the drone and the PAPI are converted from WGS-84 LLA → ECEF → ENU (a
local East-North-Up tangent frame at the PAPI), then
`elevation = atan2(Up, hypot(East, North))`. The primary
`elevation_angle_deg` is the angle to the **PAPI midpoint** (centroid
of the lamp row); a per-lamp angle (each lamp as its own ENU origin)
is also returned for the per-lamp charts. This replaces an earlier
haversine + raw-altitude-subtraction approximation — the two agree to
~0.01° internally at the 300-1000 m baselines in this dataset, but ENU
is the geodetically correct transform the client specified, and its
output was validated to **~0.02°** against the client's own tool.
(Altitude accuracy matters here: GPS extraction prefers the
RTK-corrected DJI XMP `AbsoluteAltitude` over EXIF `GPSAltitude`, whose
non-RTK vertical error would otherwise drag the angle out of the true
band.)

The client's tool reports the per-lamp red→white transition set-angles
as approximately **2.32° / 2.55° / 3.12° / 3.6°** (the four lamps).
These are **not yet bound**: `configs/papi_edny.yaml` still carries
`set_angle_deg: null` per lamp and falls back to FAA defaults
(`[2.50, 2.83, 3.17, 3.50]` for a 3.0° glideslope) with a
`transition_half_width_deg` of 0.10. These set-angles parametrise the
**offline** lamp-state labelling
(`packages/papi/src/papi/lamp_state.py:compute_lamp_state`, used by the
auto-labelling pipeline), not a runtime per-frame transition — the served
app derives `transition` temporally from observed colour flips (§5.1), so
the angle here is validated and the *offline* boundaries simply shift once
the client's set-angles are confirmed and entered. PAPI 06 uses
the data-analysis branch's `461.37 m` lamp reference; the competing
`464.988 m` notebook value is a minimum client drone EXIF/MRK altitude
floor proxy, not runtime lamp height. See the geometry caveat in the
model card.

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

`apps/frontend/src/App.jsx` is now just the route shell + theme /
language / backend-status. The upload + inference state and its
handlers were extracted into the `useAnalysis` hook, and the Live
Demo subtree receives that state through a React context
(`LiveDemoProvider` / `useLiveDemo`) instead of ~16 drilled props;
each view is its own component under `src/pages/`. The routes:

| Route | Component | Purpose |
| --- | --- | --- |
| `/` | `IntroductionPage` | Hero, project context, airport map |
| `/live-demo` | `LiveDemoPage` | Upload (media / folder) paths, frame-stage + analysis panel; reads state from `LiveDemoProvider` context |
| `/runways` | `RunwaysPage` | Manage runway geometry (select / add custom runways) used by the angle calculation |
| `/insights` | `InsightsPage` | Tabbed charts (angle-vs-state, transitions, session summary) + model/dataset metrics, all from real backend output; PDF export |
| `/history` | `HistoryPage` | Recent persisted analyses, artifacts, and model runtime status |

Theme is driven by CSS custom properties on `html[data-theme]`.
Brand identity: Intersoft navy (`#00426e`), Poppins typography,
restrained palette.

API client lives in `src/lib/api.js` — the analyze calls
(`analyzeMedia`, `analyzeFrame`, `analyzeFrames`, `analyzeSequence`)
plus the log / stats / model / runway / readiness fetchers all wrap
`fetch` (with a per-call timeout). `analyzeSequence` posts the folder
to `/api/analyze-sequence` for the folder→video path.

## 7. Deployment & operations

- **Containerised** via `compose.yaml`. Three services, one
  named network, two named volumes, three healthchecks, three
  restart policies (`unless-stopped`). The frontend nginx reverse-proxies
  `/api` + `/media` to the backend, so the browser uses a single origin.
- **Logs**: JSON file with 10 MB × 5 file rotation per service.
- **Security floor**:
  - Both runtime containers run as non-root users (`papi`, `nginx`).
  - Postgres bound to `127.0.0.1` only; service-to-service access
    via the internal compose network.
  - `PAPI_ENV=production` makes `PAPI_API_KEY` mandatory at startup.
  - nginx ships baseline security headers (CSP, X-Frame-Options,
    Referrer-Policy, Permissions-Policy, X-Content-Type-Options).
  - Process-local rate limiting per client IP (defaults: 600
    requests/min general, 60/min on the analyze endpoints; returns
    429 + `Retry-After`). uvicorn trusts the proxy's
    `X-Forwarded-For` (`FORWARDED_ALLOW_IPS`) so buckets track real
    clients, not the nginx hop.
- **CI**: GitHub Actions runs pytest + ruff + npm lint + npm build +
  Docker build on every push (`.github/workflows/ci.yml`).

## 8. Known scope limitations

| Item | Status | Where to look |
| --- | --- | --- |
| ZoomCamera auto-labelling | Skipped sprint 1 | `configs/papi_edny.yaml:79` (focal_px = null) |
| EDNY commissioned set-angles | FAA defaults used | `configs/papi_edny.yaml` (TODO comments) |
| Multi-airport generalisation | Out of scope for v1.0 | One YAML per airport; geometry library already supports it |
| Real-time inference (>10 fps) | ~0.4 fps on a laptop CPU | INT8 ONNX exists; GPU not configured |
| Edge-device deployment | Not yet measured | `docs/edge-benchmark.md` template ready for the team |

## 9. Sources of truth

- **Code structure**: this file + `README.md`
- **Labels and per-lamp state semantics**: `docs/label_spec.md`
- **Pipeline stages and their I/O**: `docs/pipeline.md`
- **Open questions and decisions**:
  [BigBrain project hub](../README.md) (`03-projects/intersoft-papi-detection`)
- **Known issues (audited 2026-05-27)**:
  [BigBrain audit](../README.md) (`03-projects/papi-codebase-audit-2026-05-27`)

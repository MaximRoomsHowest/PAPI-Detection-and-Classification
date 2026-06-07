# Phase 0 — Context & Repo Reconnaissance

Reconnaissance for the transition-aware PAPI pipeline. Every fact below was verified from
files (BigBrain vault, repo, on-disk dataset), not assumed.

## Relevant BigBrain findings

- **Client deliverable** (`03-projects/intersoft-papi-detection.md`): locate the PAPI, classify
  one of five global states, and **label each of the four lamps `white` / `red` / `in transition`**;
  robust to light/weather/perspective/occlusion; real-time + offline; reproducible eval.
- **Transition is an open methodological choice** (client, 2026-05-26): current production derives
  transitions from per-lamp colour classification; the client suggested also evaluating the
  detection-tracking method. Decision criteria: **transition recall, transition-angle MAE,
  false-transition rate** on the verification sample. → motivates our head-to-head.
- **Transition detection is the known weak point**: best top-4 test transition **F1 ≈ 0.174**
  (±1-frame tolerance). Improvement roadmap: temporal smoothing/hysteresis, hard examples around
  transition boundaries, then a larger backbone.
- **Validated geometry**: rwy-24 per-lamp set-angles reproduced to **±0.02°** against the client's
  tool using the WGS-84 LLA→ECEF→ENU transform (`packages/papi/src/papi/geometry.py`) and the
  461.37 m datum. Commissioned rwy-24 angles ≈ **[2.32, 2.55, 3.12, 3.60]°**. **rwy-06 set-angles
  still pending** (blocked on client) → rwy-06/night transition labels carry more uncertainty.
- **ByteTrack** already integrated; per-request reset fixed 2026-05-28 (`reset_tracker=frame==0`).

## Original dataset

- **Path (DO NOT MODIFY):**
  `C:\Users\rodri\source\howest\25-26\industryproject\PAPI-artifacts\2026-05-26-cleanup\data\datasets\papi_lamp_sequences\`
  (the in-repo `data/datasets/papi_lamp_sequences/` is empty, git-ignored scaffolding).
- **Size:** 8.92 GB, 6,458 files — **3,194 images, 3,194 per-frame label files, 51 CSVs**. Raw
  originals (`…/PROJECT1-PAPI/`) 11.4 GB.
- **Format:** Ultralytics **YOLO detection** — one `labels/<stem>.txt` per `images/<stem>.JPG`,
  rows `class_id cx cy w h` (normalized). Organized `daytime/` (12 flights) + `nighttime/`
  (5 flights), one folder per source video.

## Annotation format & taxonomy

- **Per-lamp**, not per-frame/global: one bbox per visible lamp (≈4 per frame).
- **Current taxonomy = 2-class:** `{0: papi_light_red, 1: papi_light_white}` in every `data.yaml`.
  No `transition` class (it was deliberately removed 2026-05-22; transitions became a temporal
  post-process).
- **Geometric 3-state already computed** by `lamp_state.py::compute_lamp_state()` →
  `white|red|transition` + angular margin, but **never baked into the YOLO labels**. This is the
  seam Phase 3 exploits.

## Temporal ordering, source IDs, splits

- **Temporal ordering preserved:** `metadata.csv` per video carries `sequence_index`, UTC/local
  timestamps, camera pose, `lat/lon/alt_ellipsoidal_m`, `nearer_runway`, `is_night`,
  `standoff_bucket_m`, and a flight-level `split` column.
- **Source video IDs:** the folder name (e.g. `DJI_202604281946_014_1000`) and `video_id` column.
- **Split strategy = flight-level** (anti-leakage). `prepare_yolo_sequence_dataset.py` already
  **enforces one split per flight** (audit W2 fix) — adjacent frames cannot leak across train/val/test.
  Test ≈ 3 flights (1000 m day wide, 300 m day zoom, 500 m night wide); val ≈ 3 flights; train = rest.
- **Tracking artifacts** per video: `tracks.csv` (per-detection `physical_lamp_id` 1..4 + bbox via
  projection, left-to-right fallback) and `transitions.csv` (consecutive-frame red↔white switches).
  Totals ≈ 12,761 track rows; ~135–151 recorded transitions.

## Model architecture & output

- **Serving model:** `models/serving/best.pt` = `yolo26s` trained at `imgsz=1280` on the 2-class
  sequence dataset (val mAP50 ≈ 0.98). Base weights in `models/base/{yolo26n,yolo26s,yolov26m}.pt`.
- **Output:** per-lamp `LampResult{index, state, confidence, bbox}` (state ∈
  `white|red|transition|obscured|unknown`), a derived `global_state`, and — for video/sequence —
  `transitions[]` (`TransitionEvent`) + `angle_track[]` (`AngleSample`).

## Inference pipeline behavior

- FastAPI backend; `InferenceService` decomposed into `frame_source / detector / angle_resolver /
  sequence_runner` (`apps/backend/app/services/inference/`).
- Endpoints: `/api/analyze` (image|video), `/api/analyze-frame` (image), `/api/analyze-frames`
  (batch images, no continuity), `/api/analyze-sequence` (folder→video, **ByteTrack + transitions**).
- Video path: per-frame `model.track(..., persist=not reset, tracker="bytetrack.yaml")` →
  `track_observations[track_id]` → `lamp_index_by_track()` (4 most-persistent tracks, left-to-right)
  → `detect_lamp_transitions()` (red↔white within ≤2 frame gap). One shared model under an `RLock`.

## CVAT import/export workflow

- Export format: **Ultralytics YOLO Detection 1.0** via `packages/papi/src/papi/cvat_export.py`
  (`build_ultralytics(class_names=…)` — already class-map parameterized; supports flat/original
  naming, train/val subsets, zip). Local CVAT repo present at `C:\Users\rodri\source\cvat`
  (not currently running).

## Risks discovered before implementation

1. **Architecture contradiction** — adding a `transition` detector class reverses the documented
   2-class decision. Resolved by user: build it *and* keep the temporal method (head-to-head).
2. **Label-resolution trap** — Ultralytics maps an image path to its label by swapping
   `/images/`→`/labels/`; a pure path-reference twin would read the *original* labels. Resolved by
   **hardlinking images into the twin** so it carries its own labels (Phase 1).
3. **Config uses FAA defaults** — `configs/papi_edny.yaml` has `set_angle_deg: null` everywhere
   (FAA `[2.50,2.83,3.17,3.50]`), not the validated commissioned rwy-24 angles. Phase 2 adds an
   **override config**; the live config is never mutated.
4. **rwy-06 set-angles pending** — night/rwy-06 transition seeds are less certain; route more of
   them to manual review.
5. **Transition class will be rare** — Phase 6 QA may trigger the "too few → stop and report" path.
6. **Datum risk** (rwy-24 altitude) — a wrong datum biases every elevation angle; spot-check catches
   gross boundary errors.

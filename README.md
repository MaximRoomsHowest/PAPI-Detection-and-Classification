# PAPI Detection and Classification

Real-time detection of a four-light **PAPI** (Precision Approach Path Indicator) installation
and per-lamp **white / red** state classification from DJI Matrice 4E drone
imagery. Howest industry project for **Intersoft Electronics Services BV**, May–June 2026.

Sprint 1 focuses on the **dataset pipeline**: extract per-image metadata, auto-generate
YOLO-format bounding-box labels from RTK GPS + gimbal pose + calibrated intrinsics (no manual
annotation), derive per-lamp state from geometry, and prepare a verification sample for CVAT.
Model training and evaluation begin in sprint 2.

## Setup

Requires **Python 3.10+** (3.11+ recommended; we run with 3.10 because that is what was
available on the dev machine — bump the floor if your CI image is newer).

```powershell
# from the repo root
py -3.10 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

### Link the raw dataset

The pipeline reads images from `data/raw/<flight>/<file>.JPG`. To avoid copying ~12 GB, create
a Windows directory junction from `data/raw` to the on-disk `PROJECT1-PAPI/`:

```powershell
# from the repo root, in cmd.exe or PowerShell (no admin needed for /J)
cmd /c mklink /J data\raw PROJECT1-PAPI
```

If that fails (e.g. cross-drive or restricted environment), copy or symlink the folder by
whatever method works — the rest of the pipeline only cares that `data/raw/<flight>/*.JPG`
resolves.

## Run the pipeline

One entrypoint: `scripts/pipeline.py` with five named stages. Run them all in order, or
target an individual stage. From the repo root with the venv active:

```powershell
# Full pipeline (extract -> calibrate -> autolabel -> sample -> export)
python scripts/pipeline.py all

# Subset: skip the slow CVAT export
python scripts/pipeline.py all --skip export

# Re-run only specific stages (useful when iterating)
python scripts/pipeline.py autolabel --limit 100
python scripts/pipeline.py export --limit 300

# Active-learning preprocessing, YOLOv26m training, and CVAT batch generation
# are orchestrated from notebooks/02_active_learning_preprocessing_template.ipynb

# Show help for any stage
python scripts/pipeline.py --help
python scripts/pipeline.py calibrate --help
```

Stage descriptions:
| Stage | Reads | Writes |
|---|---|---|
| `extract` | `data/raw/<flight>/*.JPG` | `data/interim/images_metadata.csv` |
| `calibrate` | metadata CSV (LRF-Normal frames) | `configs/projection.yaml` (DJI gimbal Euler convention) |
| `autolabel` | metadata CSV + projection.yaml | `data/labels/auto/*.txt` (YOLO) + `data/interim/lamp_state.csv` |
| `sample` | metadata + lamp state | `data/interim/verification_sample.csv` |
| `export` | sample + auto-labels + raw images | CVAT Ultralytics YOLO Detection 1.0 export. Prefer the batch scripts for CVAT Online. |

The canonical corrected dataset is now video-oriented under
`data/datasets/papi_lamp_sequences/`, split into `daytime/` and `nighttime/`.
Each source video folder contains `images/*.JPG`, matching `labels/*.txt`, and
`metadata.csv` in frame order so the frames can be reconstructed into video for
live testing. The latest validation summary is stored at
`data/datasets/papi_lamp_sequences/validation_summary.json`.

For the full active-learning preprocessing loop, use
`notebooks/02_active_learning_preprocessing_template.ipynb`. It records the
manual-correction handoff points and validates the canonical sequence dataset.
For small-model training plus temporal transition extraction, use
`notebooks/03_yolov26n_detection_tracking_training.ipynb`.

For the current detector scope, use two classes only: `papi_light_red` and
`papi_light_white`. Transitions are inferred later by tracking each individual
lamp over time and detecting red/white state changes.

Run `pytest` and `ruff check src tests scripts` before committing changes.

## Repository layout

| Path | Purpose |
|---|---|
| `PROJECT1-PAPI/` | Raw dataset (4,058 JPGs across 21 flights + `.MRK/.NAV/.OBS/.RTK/.pbk` PPK files + surveyed coords XLSX). Do not modify. |
| `data/raw/` | Junction to `PROJECT1-PAPI/`; resolved-path source the scripts read. |
| `data/interim/` | `images_metadata.csv`, `lamp_state.csv`, `verification_sample.csv`. |
| `data/labels/auto/` | YOLO `.txt` auto-labels per image (WideCamera only in sprint 1). |
| `data/labels/verified/` | Post-CVAT corrected labels (empty until verification round). |
| `data/annotations/manual_corrections/` | Human-corrected CVAT exports, grouped by correction milestone. |
| `data/datasets/papi_lamp_sequences/daytime/` | Canonical corrected daytime sequence dataset, grouped by source video. |
| `data/datasets/papi_lamp_sequences/nighttime/` | Canonical corrected nighttime sequence dataset, grouped by source video. |
| `data/datasets/papi_lamp_sequences/tracking_manifest.json` | Per-lamp track and red/white transition summary. |
| `data/datasets/papi_lamp_sequences/yolo26n_combined/` | No-copy YOLO train/val/test config for the small YOLOv26 detector. |
| `data/README.md` | Data organization rules and the current sequence dataset workflow. |
| `src/papi/` | Python package: metadata, geometry, projection, lamp-state, sampling, CVAT export, YOLO I/O. |
| `scripts/` | Numbered runnable entrypoints. |
| `configs/` | `papi_edny.yaml` (surveyed coords + camera intrinsics + set-angles), `split.yaml` (train/val/test by flight), `projection.yaml` (gimbal Euler convention; written by script 00). |
| `tests/` | `pytest` suite covering projection identity + behind-camera + LRF round-trip + lamp-state boundaries. |
| `docs/` | `label_spec.md` (annotation conventions), `pipeline.md` (full how-to-run). |
| `notebooks/` | Walkthrough notebook for one-image debugging. |

## Strategy in one paragraph

Manual annotation of 4,058 frames would consume the whole sprint. Instead we **compute
bounding boxes analytically** by projecting each surveyed PAPI light's WGS84 lat/lon/alt into
pixel coordinates using the camera's RTK GPS + gimbal yaw/pitch/roll + the `CalibratedFocalLength`
+ `CalibratedOpticalCenter` baked into the XMP of every WideCamera frame, and **compute
per-lamp white/red/transition state** by comparing the elevation angle from each PAPI light to
the drone against the light's design set-angle (3.0° glideslope, FAA-standard 2.50°/2.83°/3.17°/3.50° for
lights 1–4 until Intersoft confirms exact values). A verification sample biased toward
transition boundaries, ZoomCamera frames, and lower-confidence GPS gets manually reviewed in
CVAT; if pilot agreement passes, the rest of the auto-labels are trusted for sprint-2 training.

**Dual runway**: contrary to the initial dataset assumption ("all flights target runway 06"),
all **day flights (3,432 frames, 16 flights) target the runway 24 PAPI**; the **5 night flights
(626 frames) target runway 06**. The pipeline picks the nearer PAPI cluster per-frame.

## Status & open questions

- **Sprint 1 (this README)**: dataset pipeline + auto-labels + verification sample. In progress.
- **Pending Intersoft confirmation**:
  - Exact set-angles for the EDNY runway 06 PAPI lights (using FAA defaults as placeholders).
  - WGS84 altitude of the four PAPI lamps (using `default_alt_wgs84_m = 465.0` as placeholder).
  - ZoomCamera calibrated focal length (XMP omits it; sprint-1 auto-labels skip zoom).
- See `docs/pipeline.md` for the LRF gimbal-convention calibration result.

## Team

Four-person Howest student team. Industry contact: Daoud Yousef (Intersoft).

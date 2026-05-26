# Pipeline — how to run the sprint-1 auto-labelling end-to-end

## Prerequisites

- Python 3.10+ in a venv with `pip install -e .[dev]` done.
- `data/raw/` resolves to the archived raw artifact folder. From the repo root on Windows:
  `cmd /c mklink /J data\raw ..\PAPI-artifacts\2026-05-26-cleanup\PROJECT1-PAPI`.
- `configs/papi_edny_rwy06.yaml` and `configs/split.yaml` present (committed).

## Pipeline entrypoint

All five stages live in **one script** with argparse subcommands:
`scripts/pipeline.py`.

```powershell
python scripts/pipeline.py all                    # run everything in order
python scripts/pipeline.py all --skip export      # skip a stage
python scripts/pipeline.py all --only extract,calibrate  # run only a subset
python scripts/pipeline.py <stage>                # run a single stage
python scripts/pipeline.py <stage> --help         # per-stage flags
```

| Stage | Reads | Writes | Typical runtime |
|---|---|---|---|
| `extract` | `data/raw/<flight>/*.JPG` | `data/interim/images_metadata.csv` (4,058 rows × ~36 cols) | ~5–25 s |
| `calibrate` | metadata CSV (LRF-Normal frames) | `configs/projection.yaml` (DJI gimbal Euler convention) | ~2 s for 384 conventions × 48 frames |
| `autolabel` | metadata CSV + projection.yaml + papi_edny.yaml | `data/labels/auto/<flight>/*.txt` (YOLO bboxes, WideCamera only) + `data/interim/lamp_state.csv` (all frames) + `data/labels/data.yaml` | ~3 s |
| `sample` | metadata + lamp state | `data/interim/verification_sample.csv` | < 1 s |
| `export` | sample + auto-labels + raw images | CVAT **Ultralytics YOLO Detection 1.0** export folder with `data.yaml`, `train.txt`, `val.txt`, `images/<train\|val>/*.JPG`, and `labels/<train\|val>/*.txt`. Train/val assignment uses `configs/split.yaml`. | depends on sample size; ~60–120 s |

Dependencies: `extract` → `calibrate` → `autolabel` → `sample` → `export`. `all` runs them
in that order. The sprint-2 "compute auto-vs-human agreement" stage is not yet implemented;
will be added as a sixth subcommand once `data/labels/verified/` is populated.

### CVAT upload workflow

CVAT Online rejects uploads above 4 GiB. Use normal-only batches instead of one
large mixed export:

Run `notebooks/02_active_learning_preprocessing_template.ipynb`; it is the
single human-facing entrypoint for preprocessing, YOLOv26m training, assisted
annotation, and CVAT batch generation.

Use `notebooks/03_yolov26n_detection_tracking_training.ipynb` for the small
YOLOv26 detector run. It rebuilds per-lamp tracking annotations, prepares the
combined day/night training config, and keeps transition detection as temporal
post-processing rather than a YOLO class.

The active training/evaluation data is now the sequence dataset under
`data/datasets/papi_lamp_sequences/`. Recreate upload-ready CVAT batches from
that canonical source only when another manual review round is needed. Each
batch folder should contain exactly two CVAT archives:

1. Create the task from `images.zip`.
2. Add labels `papi_light_red` and `papi_light_white`.
3. Import `annotations.zip` as **Ultralytics YOLO Detection 1.0**.

Both archives must use the same `images/train/*.JPG` item paths. Do not use
`dataset.zip`, flat image-name archives, or legacy annotation-only artifacts for
this workflow.

## Calibration result — DJI gimbal Euler convention

The script brute-forces 384 conventions (2 ENU swaps × 6 Euler orders × 8 sign triples × 2
body→image swaps × 2 invert-rotation options) against ~48 LRF-Normal WideCamera frames spread
across 16 flights, and picks the combination with the lowest median pixel residual from
`(W/2, H/2)`. **Gate: median ≤ 100 px, max ≤ 300 px** — fails loudly otherwise.

**Concrete result from this session** (2026-05-19, full result in `configs/projection.yaml`):

| Knob | Value |
|---|---|
| ENU swap | `ENU_to_NED` = `[[0,1,0],[1,0,0],[0,0,-1]]` |
| Euler order | `ZYX` (intrinsic) |
| Signs (yaw, pitch, roll) | (+1, +1, +1) |
| Body → image swap | `[[0,1,0],[0,0,1],[1,0,0]]` |
| Invert rotation | **True** |
| Median residual | **6.1 px** |
| Max residual | **21.0 px** |
| Calibration sample | 48 frames across 16 flights |

The winning combination is the **standard aerospace ZYX-intrinsic** with `invert_rotation=True`,
meaning `Rotation.from_euler('ZYX', [yaw, pitch, roll], degrees=True).apply(ned_vec, inverse=True)`
maps the NED-frame vector into the camera body frame. DJI's gimbal Euler convention thus matches
the aerospace standard exactly — yaw cw-from-north positive, pitch nose-up positive (so the
recorded values, with -90 = looking straight down, are aerospace pitch directly).

If you re-run and the median residual exceeds 100 px, the LRF target altitude field is the
likely culprit. Sprint 1 surfaced a bug where `LRFTargetAlt` is camera-relative (e.g. `-2.4`)
while `LRFTargetAbsAlt` is the WGS84 absolute (`459.3`). Always use `lrf_target_abs_alt_m`.

## Dual-runway finding (2026-05-19)

The initial BigBrain note claimed "all flights target the standard four-light PAPI on runway
06". The pipeline disagreed: per-frame haversine distance shows **all 16 day flights (3,432
frames) target runway 24** (which has its PAPI cluster at ~(47.6735, 9.5182)), and **all 5
night flights (626 frames) target runway 06** (PAPI at ~(47.6688, 9.5040)). Folder names like
`300mday2up` refer to the runway-24 standoff, not runway 06.

`configs/papi_edny.yaml` now contains the surveyed coordinates for **both** PAPIs;
`papi.geometry.resolve_papi_for_frame` picks the nearer one per frame.

## Known limitations & TODOs

| Item | Status | Owner |
|---|---|---|
| ZoomCamera auto-labels (no `CalibratedFocalLength` in XMP) | **Skipped in sprint 1**; all 818 zoom frames are flagged for manual verification | sprint 2 |
| EDNY commissioned set-angles (both runways) | **Placeholder** (FAA defaults 2.50°/2.83°/3.17°/3.50°) | confirm with Intersoft |
| WGS84 altitude of the PAPI lamps (both runways) | **Placeholder** (`default_alt_wgs84_m = 465.0`) | confirm with Intersoft |
| RTK-Single frames (842 images, flag=16) | Auto-labels still produced, but flagged for verification (`rtk_uncertain` reason) | reviewer judgement |
| Per-lamp tight bboxes | Sprint 1 only emits one installation-level bbox | sprint 2 |
| Auto-vs-human agreement reporting | Not yet implemented (will add as `pipeline.py agreement` subcommand) | sprint 2 |
| Day vs. night error rates | Not measured yet (no verified labels yet) | sprint 2 verification round |

## Debugging tips

- `python scripts/pipeline.py extract --limit 50` — fast metadata smoke test.
- `python scripts/pipeline.py autolabel --limit 100` — auto-label first 100 frames to inspect coverage.
- `python scripts/pipeline.py export --limit 300` — small CVAT bundle for an upload smoke test.
- The notebook `notebooks/01_pipeline_walkthrough.ipynb` runs one image end-to-end with the
  intermediate matrices printed.
- If `data/raw/` does not resolve, the `extract` stage will report "Found 0 JPGs" — verify
  the junction with `dir data\raw` from cmd and confirm the archived artifacts are present.

## Verification gates (run before declaring sprint-1 done)

- [ ] `pip install -e .[dev]` succeeds from a clean venv.
- [ ] `pytest` runs and all tests pass (LRF round-trip skipped if calibration not yet run).
- [ ] `python scripts/pipeline.py extract` writes a CSV with 4,058 rows.
- [ ] `python scripts/pipeline.py calibrate` writes `configs/projection.yaml` with median residual ≤ 100 px.
- [ ] `python scripts/pipeline.py autolabel` writes ~3,240 YOLO `.txt` files (WideCamera count) + `lamp_state.csv` with 4,058 rows.
- [ ] `python scripts/pipeline.py sample` writes the verification sample with reason counts printed.
- [ ] `python scripts/pipeline.py export` writes a `.zip` that CVAT can import.
- [ ] `ruff check src tests scripts` is clean.

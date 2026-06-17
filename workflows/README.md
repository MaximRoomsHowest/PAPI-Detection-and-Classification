# Workflows

Human-facing ML and data workflows: dataset preparation, model-assisted labeling,
training, and evaluation for the PAPI light detector.

| Path | Purpose |
|---|---|
| `notebooks/` | Notebook-first data analysis, training, and evaluation workflows. |
| `scripts/` | Runnable data-prep, labeling, CVAT export, training, and evaluation entrypoints. |

## Reproduction chain (raw footage → serving model)

1. **Auto-label** — `scripts/pipeline.py` is the *active-learning / auto-labeling* pipeline
   (extract frames → calibrate → model-assisted pre-label → sample → export a CVAT bundle).
   **It does NOT train or evaluate** — it only produces candidate labels for human review.
2. **Human verification** — review/correct the pre-labels in CVAT and re-import the verified
   YOLO labels. For the transition class, `scripts/apply_verification.py` applies the
   colour-gate (`papi.transition_scoring.classify_lamp_colour`) so a flip-anchored box is kept
   as `transition` only when the crop is a *visible amber blend*, not a stable red/white.
3. **Dataset QA (gate before training)** — `scripts/qa_transition_dataset.py` validates label
   format, class balance, **flight-level split integrity (no leakage)**, file orphans, and test
   adequacy. It exits non-zero unless the dataset is training-ready.
4. **Train** — colour-detector via `notebooks/08_model_training_optimization.ipynb`; sequence /
   3-class transition model via `notebooks/03_*` or `scripts/train_transition_model.py`.
   **Training must be colour-safe**: `hsv_h=0, hsv_s=0, mosaic=0, mixup=0, copy_paste=0`
   (hue/saturation/mosaic jitter swaps red↔white↔transition and corrupts labels); horizontal
   flip reverses lamp order and is unsafe for the ordered glideslope semantics.
5. **Evaluate** — `scripts/evaluate_transition_model.py` + `notebooks/04_*`, `07_*`. Metrics are
   reported at the **val-default conf for the full PR curve**, distinct from the serving
   operating point — see `models/MODELS.md` for the honest, threshold-tagged numbers.
6. **Promote** — copy the chosen checkpoint into `models/serving/` per `models/MODELS.md` §5.

## Split policy (must read)

Splits are **flight-level**, not per-frame: whole flights go to exactly one of train/val/test so
adjacent near-duplicate frames cannot leak across splits. The canonical assignment is
[`configs/split.yaml`](../configs/split.yaml), enforced by `scripts/prepare_yolo_sequence_dataset.py`
and checked by `scripts/qa_transition_dataset.py`. **Never** split video-derived frames randomly
per-frame (it inflates metrics via near-duplicate leakage).

## Script & notebook reference

Not every file here is part of the daily critical path — many are one-off
reproducibility steps. Use this map to tell them apart.

### Notebooks (`notebooks/`)

| Notebook | Role |
|---|---|
| `01_pipeline_walkthrough` | Single-image, end-to-end walkthrough — handy for debugging projection changes. |
| `02_model_assisted_labelling` | **Active** — 2-class detection training + CVAT batch generation. |
| `03_yolov26n_detection_tracking_training` | **Active** — detector training (day/night combined). |
| `04_yolov26n_sequence_model_evaluation` | Evaluation + per-class metrics / confusion. |
| `05_data_analysis` | Dataset profiling and exploratory analysis (referenced by `docs/data-card.md`). |
| `06_data_augmentation` | Augmentation-strategy exploration (reference). |
| `07_model_performance` | Model-performance analysis (reference). |
| `08_model_training_optimization` | Colour-safe detector-training reference. |
| `09_weather_evaluation` | Weather-robustness evaluation (rain/fog/haze; see `models/runs/README.md`). |

### Scripts (`scripts/`), grouped by purpose

- **Pipeline entrypoint** — `pipeline.py` (+ shared `_pipeline_utils.py`): the auto-labelling pipeline (extract → calibrate → pre-label → sample → export).
- **Dataset build / prep** — `prepare_yolo_sequence_dataset.py`, `build_sequence_tracking.py`, `build_eval_seed.py` (the committed evaluation seeds).
- **Verification / QA gate** — `apply_verification.py` (colour-gate), `qa_transition_dataset.py` (the pre-training split-leak gate).
- **Training** — `train_detector_model.py`, `train_transition_model.py` (+ `weather_aug.py` for synthetic-weather augmentation).
- **Evaluation / metrics** — `evaluate_builtin.py`, `evaluate_transition_model.py`, `run_redwhite_test_eval.py`, `build_redwhite_test_view.py`, `populate_model_metrics.py`.
- **Benchmark** — `edge_benchmark.py`, `backend_bench.py`.

## Authoritative model doc

[`models/MODELS.md`](../models/MODELS.md) is the source of truth for model lineage, training args,
and metrics (with their measurement thresholds and small-sample caveats).

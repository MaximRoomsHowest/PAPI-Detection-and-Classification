# Model Registry — PAPI Vision

> Source of truth for every trained / deployed model artifact in this
> repository. Updated whenever a new training run lands in `models/runs/`
> or whenever the serving slot rotates.
>
> Companion to [`models/README.md`](README.md) (which covers the local
> filesystem layout). This file covers **lineage, metrics, and deployment
> status** — the things you need to roll back or roll forward responsibly.

## 0. Naming convention (read this first)

Every run folder is named **`<arch>-<dataset>-<resolution>`** so the name
alone tells you which model it is — no need to open the file:

- `<arch>` — `yolo26n` (≈2.6 M params, fast), `yolo26s` (≈9.1 M, accurate),
  `yolov8s` (legacy comparison).
- `<dataset>` — `baseline` (first cut), `augmented` (image-augmentation
  experiment), `fulldata` (full labelled set), `sequence` (red/white
  sequence set), `transfer` (transfer-learning seed).
- `<resolution>` — training `imgsz` in px (`640` / `1280`) when it
  distinguishes two otherwise-identical runs.

Inside every run folder the weights keep Ultralytics' conventional
`weights/best.pt` + `weights/last.pt` names — tooling
(`populate_model_metrics.py`, `yolo val`) depends on that, so only the
**folder** carries the descriptive name.

The **serving slot** is always `models/serving/best.pt` (a copy of the
chosen run's `best.pt`). The slot filename is intentionally stable — the
Dockerfile, `compose.yaml`, `.env`, and the promotion procedure (§5) all
point at it, so swapping models means copying a new file into the slot,
**not** renaming the slot. Which run is currently in the slot is recorded
in `models/serving/model_card.json` (`model_id`) and in §3.1 below.

The **runtime selector registry** is `models/serving/models.json`. The backend
serves it through `GET /api/models`, checks whether each weight exists, and
uses its `role` to choose the default transition derivation: 2-class detector
models use temporal tracking, while the 3-class transition classifier uses
learned transition events.

| Selector id | Run / path | Role | Default behavior |
| --- | --- | --- | --- |
| `small` | `models/serving/best.pt` → `yolo26s-fulldata-1280` | detector | Default model; transitions via tracking |
| `nano` | `models/runs/yolo26n-sequence-1280/weights/best.pt` | detector | Previous serving model; transitions via tracking |
| `transition` | `data/runs/detect/transition3class-yolo26s-1280/weights/best.pt` | transition | Optional ignored artifact; transitions via learned model events |

### Rename map (2026-05-31)

The old Ultralytics auto-names were renamed to the convention above. The
historical benchmark records under `docs/qa-artifacts/benchmarks/` still
reference the **old** paths (they record what was run at that time and are
left intact); use this map to trace them:

| Old name | New name |
| --- | --- |
| `train-2` | `yolo26n-baseline` |
| `train-3` | `yolo26s-baseline` |
| `train-5` | `yolo26s-augmented` |
| `train-6` | `yolo26s-fulldata-640` |
| `train-7` | `yolo26s-fulldata-1280` *(now serving)* |
| `yolo26n_sequence_red_white_safe` | `yolo26n-sequence-1280` *(previous serving)* |
| `modeltransfered` | `yolov8s-transfer` |

## 1. Record shape

| Field | Meaning |
| --- | --- |
| `path` | Path under `models/` |
| `arch` | YOLO variant, params in millions |
| `dataset` | Snapshot the model was trained on |
| `training` | Pointer to `args.yaml` + `results.csv` inside the run folder |
| `eval` | Per-class metrics on the held-out test split |
| `status` | `serving` / `previous` / `comparison` / `archived` |
| `notes` | Caveats, known failures, why we kept or retired it |

## 2. Base weights

Upstream Ultralytics base weights — starting points for fine-tuning, never
deployed directly.

| File | Arch | Params | Notes |
| --- | --- | --- | --- |
| `models/base/yolo26n.pt` | n | ≈ 2.6 M | Smallest, INT8-friendly; quick retraining baseline |
| `models/base/yolo26s.pt` | s | ≈ 9.1 M | Mid-size; base of the **serving** model |
| `models/base/yolov26m.pt` | m | ≈ 24 M | Accuracy ceiling for active-learning experiments |

## 3. Trained runs

### 3.1 `yolo26s-fulldata-1280` — **CURRENT SERVING** ⭐

> The higher-resolution full-dataset run from the `data_analysis` branch
> (MaximRoomsHowest, commit `d2b8b8f` "trained new model on higher
> resolution", was `train-7`). Promoted to serving on **2026-05-31** —
> substantially more accurate than the previous yolo26n model (§3.2).

| Field | Value |
| --- | --- |
| **Path** | `models/runs/detect/yolo26s-fulldata-1280/` |
| **Arch** | yolo26s (≈ 9.1 M params) |
| **Base** | `models/base/yolo26s.pt` |
| **Classes** | 2 — `PAPI-Red` (0), `PAPI-White` (1) |
| **Dataset** | Full labelled PAPI set (`PAPI_Split/data.yaml`) |
| **imgsz** | 1280 |
| **Epochs** | 100 configured, early-stopped at 54 (patience 15); `best.pt` = epoch 39 |
| **Training config** | `models/runs/detect/yolo26s-fulldata-1280/args.yaml` |
| **Training log** | `models/runs/detect/yolo26s-fulldata-1280/results.csv` |
| **Status** | **serving** (copied to `models/serving/best.pt`; card `model_id=yolo26s-fulldata-1280`) |
| **Known behaviour** | More precise than the old model → more conservative on faint lamps. On a single dim still-frame the weakest of the 4 lamps can score ≈0.34, below the `PAPI_CONFIDENCE_THRESHOLD=0.4` gate, so that one frame reads "unknown"; video aggregation recovers all 4. Lower the threshold to ≈0.3 if single-frame 4-lamp recall matters more than precision. |

#### 3.1.1 Validation metrics (auto-filled from `results.csv`)

Generated by `python workflows/scripts/populate_model_metrics.py models/runs/detect/yolo26s-fulldata-1280 --write-model-card models/serving/model_card.json`.
These are **validation-split box (B) detection** metrics — not the held-out
test regime and not per-class. Per-regime / per-state **test** numbers come
from the evaluation notebook (`04_*`), which the team owns.

| Selection | Epoch | precision | recall | mAP@0.5 | mAP@0.5:0.95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| best fitness | 39 | 0.9479 | 0.9367 | 0.9828 | 0.6791 |
| final epoch | 54 | 0.9367 | 0.9363 | 0.9816 | 0.6684 |

#### 3.1.2 Held-out test eval (per regime / per state)

| Metric | Day rwy 24 Wide | Night rwy 06 Wide | Day rwy 24 Zoom | Aggregate |
| --- | ---: | ---: | ---: | ---: |
| Detection F1 | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> |
| Per-state F1 — red | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> |
| Per-state F1 — white | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> |
| mAP@0.5 | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> |

Fill from `04_yolov26n_sequence_model_evaluation.ipynb` after the final eval run.

### 3.2 `yolo26n-sequence-1280` — previous serving (superseded 2026-05-31)

| Field | Value |
| --- | --- |
| **Path** | `models/runs/yolo26n-sequence-1280/` |
| **Arch** | yolo26n (≈ 2.6 M params) |
| **Base** | `models/base/yolo26n.pt` |
| **Classes** | 2 — `papi_light_red` (0), `papi_light_white` (1) |
| **imgsz** | 1280 |
| **Status** | **previous** — kept for rollback (see §5.9) |
| **Val metrics** | best (epoch 30): P 0.8613, R 0.8706, mAP@0.5 0.9141, mAP@0.5:0.95 0.4740 |
| **Why retired** | yolo26s-fulldata-1280 beats it on every val metric (mAP@0.5 0.983 vs 0.914, mAP@0.5:0.95 0.679 vs 0.474). |

#### 3.2.1 INT8 ONNX export — `models/serving/best_int8.onnx`

| Field | Value |
| --- | --- |
| **Path** | `models/serving/best_int8.onnx` |
| **Source model** | the **previous** `yolo26n-sequence-1280` (NOT the current serving model) |
| **Status** | **experimental + stale** — quantised from the retired yolo26n model |
| **Failure** | CPU ONNX Runtime raises `ConvInteger(10) not implemented`; runnable only on GPU-accelerated ORT. |
| **Follow-up** | Re-export INT8 from `yolo26s-fulldata-1280` once an edge target is confirmed; kept in place for now because the edge-benchmark records (`docs/edge-benchmark.md`, `docs/qa-artifacts/`) reference this exact file. |

### 3.3 Comparison / experiment runs

Empirical input for the alternative-model comparison
(`docs/deliverables/06-model-comparison.md`). Val-split metrics are read
straight from each run's `results.csv`.

| Run | Arch | Dataset / imgsz | Path | Notes |
| --- | --- | --- | --- | --- |
| `yolo26n-baseline` | yolo26n | baseline | `models/runs/detect/yolo26n-baseline/` | Early baseline; also has `weights/best.onnx` (fp32 export used in edge benchmarks) |
| `yolo26s-baseline` | yolo26s | baseline | `models/runs/detect/yolo26s-baseline/` | Baseline yolo26s |
| `yolo26s-augmented` | yolo26s | augmented | `models/runs/detect/yolo26s-augmented/` | Image-augmentation experiment |
| `yolo26s-fulldata-640` | yolo26s | full dataset, 640 | `models/runs/detect/yolo26s-fulldata-640/` | Full-dataset at 640; the 1280 sibling (§3.1) supersedes it |
| `yolov8s-transfer` | yolov8s | transfer | `models/runs/detect/yolov8s-transfer/` | Legacy YOLOv8 transfer seed; comparison only |
| `val`, `val-2…4` | yolo26s | validation passes | `models/runs/detect/val*/` | PR/F1 curves + confusion matrices, no weights |

## 4. Deprecated / archived runs

Historical training artefacts live outside the repo at
`..\PAPI-artifacts\2026-05-26-cleanup\runs\papi\`. Do **not** use these for
the integrated app unless explicitly comparing historical experiments —
they predate the two-class label spec, the dual-runway resolution, and the
final calibration.

| Archived run | Why archived |
| --- | --- |
| `yolo11n-*` | YOLO11 early experiment; replaced by the YOLO26 family |
| Pre-2026-05-26 yolo26n runs | Single-runway assumption; replaced |
| Three-class transition runs | Replaced by two-class + geometric transition (design doc §6/§11) |

## 5. Deployment promotion procedure

When promoting a new run to serving:

1. Train and evaluate in `models/runs/detect/<arch>-<dataset>-<res>/`.
2. Update §3 of this file with the new run record + metrics.
3. Add the run to `docs/deliverables/06-model-comparison.md`.
4. Compute the eval delta vs the current serving model on the held-out test
   split. If detection F1 regresses by more than **1 pp**, escalate before
   promoting.
5. Copy the new weight into the serving slot (the slot filename never changes):
   ```powershell
   Copy-Item models\runs\detect\<new_run>\weights\best.pt models\serving\best.pt -Force
   ```
6. Regenerate the model card so `/api/model` reports the new run:
   ```powershell
   ..\..\.venv\Scripts\python.exe workflows\scripts\populate_model_metrics.py `
     models\runs\detect\<new_run> --write-model-card models\serving\model_card.json
   ```
7. Restart the backend (`docker compose restart backend`, or the uvicorn
   process). The model is pre-warmed at startup, so a load error surfaces
   immediately.
8. Confirm `models/serving/models.json` still points at the intended serving
   slot and update any selector labels/metrics if the promoted run changes.
9. Run the backend + papi pytest suites and a smoke inference. Roll back if
   anything fails.
10. **Rollback**: the previous serving model is preserved in its run folder.
   Restore with:
   ```powershell
   Copy-Item models\runs\yolo26n-sequence-1280\weights\best.pt models\serving\best.pt -Force
   ```
   then regenerate the card (step 6, pointing at `models\runs\yolo26n-sequence-1280`)
   and restart the backend.

## 6. Open items

- ZoomCamera `calibrated_focal_px` is `null` in `configs/papi_edny.yaml`;
  zoom-camera frames are degraded for every model here until that lands.
- Set-angles for both runways are FAA defaults; no commissioned-angle
  override yet.
- INT8 path: re-export from the new serving model (§3.2.1) once an edge
  target is fixed; current `best_int8.onnx` is the retired model's export
  and CPU-broken.

## 7. Sources

- Layout convention: `models/README.md`
- Training notebooks: `workflows/notebooks/03_*`, `04_*`, `05_*`, `08_*`
- Eval methodology: `docs/edge-benchmark.md §5.3` for accuracy-delta protocol
- Architecture: `docs/architecture-overview.md §5.1` for two classes + geometric transition

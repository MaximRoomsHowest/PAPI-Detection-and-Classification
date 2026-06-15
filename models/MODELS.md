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

> ⚠ These val numbers are on the `PAPI_Split` validation split, which is a **random
> per-frame** partition (not flight-level) — its frames are near-duplicates of
> training frames, so the metrics are **optimistic**. See the leakage caveat in §3.1.2.

| Selection | Epoch | precision | recall | mAP@0.5 | mAP@0.5:0.95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| best fitness | 39 | 0.9479 | 0.9367 | 0.9828 | 0.6791 |
| final epoch | 54 | 0.9367 | 0.9363 | 0.9816 | 0.6684 |

#### 3.1.2 Held-out test eval (per regime / per state)

Measured 2026-06-10 on the flight-level test split (`configs/split.yaml`) via
`workflows/scripts/run_redwhite_test_eval.py` over the 2-class test view built by
`workflows/scripts/build_redwhite_test_view.py` (same frames and human-corrected
red/white boxes as the sequence dataset; the 6 test transition boxes restored to
their tracked colours). Full PR curve (val-default conf), IoU 0.5. Artifact:
`docs/qa-artifacts/test-split-eval.json`.

| Metric | Day rwy 24 Wide (1000 m) | Night rwy 06 Wide (500 m) | Day rwy 24 Zoom | Aggregate |
| --- | ---: | ---: | ---: | ---: |
| Detection F1 | 0.989 | 0.828 | not evaluated\* | 0.915 |
| Per-state F1 — red | 0.993 (n=407) | 0.800 (n=360) | not evaluated\* | 0.901 (n=767) |
| Per-state F1 — white | 0.985 (n=373) | 0.856 (n=256) | not evaluated\* | 0.928 (n=629) |
| mAP@0.5 | 0.994 | 0.886 | not evaluated\* | 0.971 |

\* The day-zoom test flight is not part of the evaluated twin dataset (ZoomCamera
`calibrated_focal_px` still pending from Intersoft) — reported absent, not zero.
Night-wide is the hard test regime; (n) are GT box counts, so the night numbers
rest on 616 boxes, not a handful. The previous serving model's numbers on the same
split are in §3.2.1a — yolo26s wins the night regime by ~10 mAP@0.5 points, which
is the promotion justification on held-out data.

> ⚠ **Leakage + augmentation caveat (pending retrain).** This checkpoint trained on
> `PAPI_Split`, built by a **random per-frame shuffle** of all merged frames
> (`data/data_analysis.ipynb`), **not** a flight-level split. Because the footage is
> video-like (adjacent near-duplicate frames), frames from the flight-level test
> flights above were also in this model's *training* set — so these "held-out"
> numbers **overlap training and are optimistic, not a clean held-out estimate**.
> Its [`args.yaml`](runs/detect/yolo26s-fulldata-1280/args.yaml) also shows
> Ultralytics' default colour-jitter augmentation (`hsv_h=0.015`, `hsv_s=0.7`,
> `mosaic=1.0`), which is risky for a red/white **colour** detector: hue/saturation
> jitter can push samples across the colour boundary while labels stay fixed. The
> §3.2.1a comparison is still apples-to-apples (same harness; both models pre-date the
> flight split), but read the absolute values as an **upper bound**. **Remediation:**
> retrain on the flight-level split ([`configs/split.yaml`](../configs/split.yaml))
> with colour-safe augmentation (`hsv_h=0, hsv_s=0, mosaic=0, mixup=0, copy_paste=0`,
> no horizontal flip); see §6 Open items.

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

#### 3.2.1a Held-out test eval (same split/harness as §3.1.2, measured 2026-06-10)

| Metric | Day rwy 24 Wide (1000 m) | Night rwy 06 Wide (500 m) | Aggregate |
| --- | ---: | ---: | ---: |
| Detection F1 | 0.984 | 0.751 | 0.877 |
| Per-state F1 — red | 0.990 | 0.700 | 0.855 |
| Per-state F1 — white | 0.977 | 0.788 | 0.893 |
| mAP@0.5 | 0.993 | 0.786 | 0.949 |

Artifact: `docs/qa-artifacts/test-split-eval.json`. Both models are near-ceiling on
the day-wide flight; the night regime separates them (yolo26s mAP@0.5 0.886 vs
0.786) — the test-split evidence behind the §3.1 promotion.

#### 3.2.1 ONNX exports

**fp32 — `models/runs/detect/yolo26s-fulldata-1280/weights/best.onnx`** (new, 2026-06-10):
exported from the SERVING yolo26s checkpoint (`yolo export format=onnx imgsz=1280
simplify=True`, onnx 1.21 / opset 19) and parity-checked against torch on 10
held-out test frames: identical box/class outputs (40/40 boxes), max confidence
drift 0.03. This is the supported non-PyTorch serving path (loadable by the
backend's registry — `.onnx` is on the weight-type allowlist).

**INT8 — retired.** The old `models/serving/best_int8.onnx` was quantised from the
RETIRED yolo26n model and fails on CPU ORT (`ConvInteger(10)` not implemented). A
re-quantisation attempt from the new yolo26s fp32 export (onnxruntime 1.20
`quantize_dynamic`) crashed the quantiser outright (2026-06-10, segfault), so there
is NO working INT8 artifact and no INT8 numbers anywhere in the docs. Revisit with
a static-QDQ pipeline once an edge target (WL051) is confirmed; until then the
fp32 ONNX export above is the deployment alternative to PyTorch.

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
6. Regenerate the model card so `/api/model` reports the new run. From the
   repo root:
   ```powershell
   .venv\Scripts\python.exe workflows\scripts\populate_model_metrics.py `
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

## 5b. Reproducibility record

What was ACTUALLY used (read from each run's committed `args.yaml` — no
retro-claims):

| Run | seed | deterministic | imgsz | batch | epochs (trained) | wall time |
| --- | ---: | --- | ---: | ---: | --- | ---: |
| `yolo26s-fulldata-1280` | 0 | true | 1280 | 4 | 100 cfg, stopped at 54 | ≈5.2 h |
| `yolo26n-sequence-1280` | 42 | true | 1280 | 2 | 100 cfg, stopped at 50 | ≈8.9 h |

Both trained on the project laptop (RTX 4070 Laptop GPU, 8 GB). Note the seeds
differ between runs — they were independent training sessions, recorded as-is.

To reproduce the held-out test evaluation (from the repo root):

```powershell
.venv\Scripts\python.exe workflows/scripts/build_redwhite_test_view.py
.venv\Scripts\python.exe workflows/scripts/run_redwhite_test_eval.py
# transition model (3-class twin):
.venv\Scripts\python.exe workflows/scripts/evaluate_transition_model.py --no-examples
```

Raw flights are not git-versioned (size); dataset identity is pinned by the
twin's `manifest.json` / `tracking_manifest.json` plus the per-box label-gate
audit trail (`verification_log.csv`). Delete `**/labels.cache` after ANY
relabeling — Ultralytics does not invalidate it (this silently fed a stale
label set to an earlier eval).

## 5c. Enabling the optional transition classifier

The 3-class `transition` registry entry ships disabled-by-default: its weights are
an experimental local artifact (`data/runs/detect/transition3class-yolo26s-1280/`),
not committed. The selector button in the Live Demo stays greyed out until the
backend can see the file. Two working recipes:

**Bare-metal / local uvicorn** — nothing to do if the training run is present:
the registry path `data/runs/detect/transition3class-yolo26s-1280/weights/best.pt`
resolves against the repo root. (Optionally override with
`PAPI_TRANSITION_MODEL_PATH=<path>`.)

**Docker Compose** — the container only mounts `./models`, so a `data/...` path
can NEVER resolve inside it (it lands at the unmounted `/app/data/...`). Place
the weights inside the mount and reference the in-container path:

```powershell
New-Item -ItemType Directory -Force models\transition | Out-Null
Copy-Item data\runs\detect\transition3class-yolo26s-1280\weights\best.pt models\transition\best.pt
# .env (models/transition/ is gitignored, so the copy is never committed):
#   PAPI_TRANSITION_MODEL_PATH=/models/transition/best.pt
docker compose up -d backend   # env change only — no rebuild needed
```

Verify: the startup log prints `Registry models loaded at startup: ... transition`
and `/api/models` reports the entry `available: true`. Selecting it in the UI
auto-uses the learned `model` transition method (`transition_method: "model"` on
the payload); `PAPI_TRANSITION_METHOD=model` does the same for the default model
when the entry is available.

**Honesty note**: enabling it makes the classifier *selectable*, not *good* —
held-out transition-class F1 is 0.10 (recall 2/6, support 6; §3.1.2 / the
registry's inline `val_metrics`). `tracking` stays the default method until the
CVAT relabel grows the transition class (§6).

## 6. Open items

- **Retrain the serving detector without leakage / colour-jitter (highest priority).**
  `yolo26s-fulldata-1280` trained on the random per-frame `PAPI_Split` with default
  colour-jitter augmentation (see the §3.1.2 caveat). Retrain on the flight-level split
  (`configs/split.yaml`) with colour-safe settings (`hsv_h=0, hsv_s=0, mosaic=0,
  mixup=0, copy_paste=0`, no h-flip) and re-report metrics on the matching held-out
  partition. The colour-safe recipe already exists in
  `workflows/scripts/train_transition_model.py` (3-class) — mirror its aug block for
  the 2-class detector.
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

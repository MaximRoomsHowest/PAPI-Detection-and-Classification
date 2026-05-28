# Model Registry — PAPI Vision

> Source of truth for every trained / deployed model artifact in
> this repository. Updated whenever a new training run lands in
> `models/runs/` or whenever the serving symlink rotates.
>
> Companion to [`models/README.md`](README.md) (which covers the
> local filesystem layout). This file covers **lineage, metrics,
> and deployment status** — the things you need to roll back or
> roll forward responsibly.
>
> **Rubric**: LR1D band-lift evidence — "model fine-tuning" and
> "compares models against each other" (10-12) plus "model
> registry / lineage" (16+ "future-proof model").

## 1. Conventions

Every model record has the same shape:

| Field | Meaning |
| --- | --- |
| `id` | Stable identifier, format `<arch>-<run>` (e.g. `yolo26n-seq-red-white-safe`) |
| `path` | Path under `models/` |
| `arch` | YOLO 26 variant (n / s / m), params in millions |
| `dataset` | Snapshot the model was trained on (commit SHA + split file) |
| `training` | Pointer to args.yaml + results.csv inside the run folder |
| `eval` | Per-class metrics on the held-out test split |
| `status` | `serving` / `staging` / `archived` / `experimental` |
| `notes` | Free-text caveats, known failures, why we kept or retired it |

## 2. Base weights

These are the upstream Ultralytics base weights — used as starting
points for fine-tuning, never deployed directly.

| File | Arch | Params | Source | Notes |
| --- | --- | --- | --- | --- |
| `models/base/yolo26n.pt` | n | ≈ 2.6 M | Ultralytics official | Quick local retraining baseline; smallest INT8-friendly |
| `models/base/yolo26s.pt` | s | ≈ 9.1 M | Ultralytics official | Mid-size baseline for accuracy comparison |
| `models/base/yolov26m.pt` | m | ≈ 24 M | Ultralytics official | Accuracy ceiling for the active-learning experiments |

**Lineage rule:** changing a base weight invalidates every
downstream run. If a base weight is retrained or replaced, bump the
filename to a versioned form (`yolo26n-v2.pt`) and update every run
that consumed it below.

## 3. Trained runs

### 3.1 `yolo26n-seq-red-white-safe` (current serving)

| Field | Value |
| --- | --- |
| **Path** | `models/runs/yolo26n_sequence_red_white_safe/` |
| **Arch** | yolo26n (≈ 2.6 M params) |
| **Base** | `models/base/yolo26n.pt` |
| **Classes** | 2 — `papi_light_red` (0), `papi_light_white` (1) |
| **Dataset** | EDNY sequence dataset, snapshot at git SHA <!-- TEAM: paste the SHA used to build the training split --> |
| **Split** | `configs/split.yaml` — flight-level, regime-aware (1000 m day wide / 300 m day zoom / 500 m night wide held out as test) |
| **Training config** | `models/runs/yolo26n_sequence_red_white_safe/args.yaml` |
| **Training log** | `models/runs/yolo26n_sequence_red_white_safe/results.csv` |
| **Epochs** | <!-- TEAM --> |
| **Augmentation** | <!-- TEAM: summary line — e.g. "default Ultralytics + nighttime brightness jitter" --> |
| **Status** | **serving** (alias at `models/serving/best.pt`) |
| **Eval (held-out test)** | see §3.1.1 |
| **INT8 ONNX export** | `models/serving/best_int8.onnx` — see §3.1.2 |
| **Known issues** | (1) `best_int8.onnx` fails on CPU ONNX Runtime (`ConvInteger(10)` not implemented). (2) ZoomCamera frames degraded — zoom focal length unconfirmed in `configs/papi_edny.yaml`. |

#### 3.1.1 Eval metrics (held-out test split)

| Metric | Day rwy 24 Wide | Night rwy 06 Wide | Day rwy 24 Zoom | Aggregate |
| --- | ---: | ---: | ---: | ---: |
| Detection F1 | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> |
| Per-state F1 — red | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> |
| Per-state F1 — white | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> |
| Per-state F1 — transition (geometric, post-hoc) | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> |
| mAP@0.5 | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> |
| mAP@0.5:0.95 | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> |

Fill these in from `04_yolov26n_sequence_model_evaluation.ipynb` after
the final eval run.

#### 3.1.2 INT8 ONNX export — `best_int8.onnx`

| Field | Value |
| --- | --- |
| **Path** | `models/serving/best_int8.onnx` |
| **Source PT** | `models/serving/best.pt` |
| **Export tool** | <!-- TEAM: e.g. `yolo export model=best.pt format=onnx int8=True` --> |
| **Status** | **experimental** — see Known issues §3.1 |
| **Failure** | CPU ONNX Runtime raises `ConvInteger(10) not implemented`. Runnable only on GPU-accelerated ONNX Runtime. |
| **Remediation** | (a) Re-export with `--opset 18+` to use the wider operator set; (b) test on Jetson Orin Nano ORT GPU EP; (c) document GPU-only deploy path if both fail. |

### 3.2 `yolo26s-comparison` (alternative-model comparison)

> Trained for the alternative-model comparison required for LR1D
> 16+ "alternative AI models implemented when they add value". See
> `docs/deliverables/06-model-comparison.md` for the head-to-head.

| Field | Value |
| --- | --- |
| **Path** | `models/runs/yolo26s_comparison/` <!-- TEAM: create this run when training completes --> |
| **Arch** | yolo26s (≈ 9.1 M params) |
| **Base** | `models/base/yolo26s.pt` |
| **Classes** | Same as §3.1 |
| **Dataset** | Same as §3.1 |
| **Split** | Same as §3.1 |
| **Training config** | <!-- TEAM --> |
| **Epochs** | <!-- TEAM --> |
| **Status** | **<!-- TEAM: staging until comparison decision --></sub>** |
| **Eval (held-out test)** | see `06-model-comparison.md` |

### 3.3 `yolo26m-comparison` (optional larger comparator)

| Field | Value |
| --- | --- |
| **Path** | `models/runs/yolo26m_comparison/` <!-- TEAM: optional --> |
| **Arch** | yolo26m (≈ 24 M params) |
| **Base** | `models/base/yolov26m.pt` |
| **Status** | **<!-- TEAM: experimental — only if time permits before final --></sub>** |
| **Notes** | Accuracy ceiling for the trade-off analysis. May exceed real-time fps target on every edge tier below the NUC. |

### 3.4 `data_analysis` runs (merged 2026-05-28)

> Brought in from the `data_analysis` branch (MaximRoomsHowest). These
> are committed **in-repo** under `data/runs/detect/` (binary weights +
> training images), unlike the `models/runs/` convention above — kept
> as-is per the integration decision. The lineage below is recovered
> from that branch's README stub; only train-6 and train-7 artifacts
> were actually committed.

| Run | Arch | Dataset / imgsz | Artifacts in repo | Notes |
| --- | --- | --- | --- | --- |
| train-2 | yolo26n | baseline | — (referenced only) | Lineage reference; weights not committed |
| train-3 | yolo26s | baseline | — (referenced only) | Lineage reference; weights not committed |
| train-5 | yolo26s | augmented dataset | — (referenced only) | Lineage reference; weights not committed |
| **train-6** | **yolo26s** | **full dataset, 640×640** | `data/runs/detect/train-6/weights/{best,last}.pt` | Full-dataset train + validation (commit 181860e) |
| **train-7** | **yolo26s** | **full dataset, 1280×1280** | `data/runs/detect/train-7/weights/{best,last}.pt` | Higher-resolution model (commit d2b8b8f); `epochs=100, batch=4` |
| val-4, val-5 | yolo26s | validation passes | `data/runs/detect/val-{4,5}/` | PR/F1 curves + confusion matrices, no weights |

The PAPI-24 reference-height angle work (commit 11973a7) lives in the
analysis notebooks (`workflows/notebooks/07_model_performance.ipynb`,
`08_model_training_optimization.ipynb`), not in `apps/` or `packages/`.

**Reconciliation note:** these yolo26s runs are the empirical input for
the alternative-model comparison in §3.2 and
`docs/deliverables/06-model-comparison.md` — the comparison is no longer
purely TEAM-todo, train-6/train-7 metrics can be read from
`data/runs/detect/train-{6,7}/results.csv`. Two storage conventions now
coexist (`models/runs/` vs `data/runs/detect/`); unifying them is a
follow-up cleanup, not done here to avoid rewriting the colleague's
committed paths.

## 4. Deprecated / archived runs

Historical training artefacts live outside the repo at:

```
..\PAPI-artifacts\2026-05-26-cleanup\runs\papi\
```

Do **not** use these checkpoints for the integrated app unless
explicitly comparing historical experiments. They predate the
two-class label spec (some have a third `transition` class), the
dual-runway resolution, and the final calibration result.

| Archived run | Why archived |
| --- | --- |
| `yolo11n-*` | YOLO11 was an early experiment; replaced by YOLO26 family |
| Pre-2026-05-26 yolo26n runs | Used single-runway assumption; replaced by dual-runway aware model |
| Three-class transition runs | Replaced by two-class + geometric transition (design doc §6 / §11) |

## 5. Deployment promotion procedure

When promoting a new run to serving:

1. Train and evaluate in `models/runs/<new_run>/`.
2. Update §3 of this file with the new run record.
3. Add the run to the comparison table in `docs/deliverables/06-model-comparison.md`.
4. Compute the eval delta vs the currently-serving model on the held-out test split. If detection F1 regresses by more than **1 percentage point**, escalate to the team before promotion.
5. Copy the new weight to the deployment alias:
   ```powershell
   Copy-Item models\runs\<new_run>\weights\best.pt models\serving\best.pt -Force
   ```
6. If the INT8 path is in scope: re-export `best_int8.onnx` (Ultralytics `yolo export`), re-run the §3.1.2 sanity check.
7. Restart the backend container (`docker compose restart backend`) — model is lazy-loaded on first request, so cold-start of the first inference will surface any load error.
8. Run the 43-test backend suite + 15-test papi suite + the user-testing-rerun smoke commands. If any test fails, roll back via step 9.
9. **Rollback**: keep the previous `best.pt` at `models/serving/best.pt.previous` for one full sprint after promotion. Restore with:
   ```powershell
   Copy-Item models\serving\best.pt.previous models\serving\best.pt -Force
   docker compose restart backend
   ```

## 6. Open items

- ZoomCamera `calibrated_focal_px` is `null` in `configs/papi_edny.yaml`. Zoom-camera frames are degraded for every model in this registry until that lands. <!-- TEAM: status after sprint 4 -->
- Set-angles for both runways are FAA defaults; no commissioned-angle override yet. <!-- TEAM: status after 2026-06-01 client meeting -->
- INT8 CPU path remains experimental — see §3.1.2.

## 7. Sources

- Layout convention: `models/README.md`
- Training notebooks: `workflows/notebooks/03_*`, `04_*`, `05_*`
- Eval methodology: `docs/edge-benchmark.md §5.3` for accuracy-delta protocol
- Architecture: `docs/architecture-overview.md §5.1` for why two classes + geometric transition

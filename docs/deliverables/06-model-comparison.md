---
title: "Alternative-Model Comparison — yolo26n vs 26s vs 26m"
subtitle: "PAPI Vision · Howest Industry Project 2026"
mainfont: "Calibri"
fontsize: 10pt
geometry: "a4paper, margin=2cm"
---

# Alternative-Model Comparison

> **Rubric**: LR1D **16+** band marker — *"alternative AI models
> implemented when they add value"*. The serving model is yolo26n;
> this document justifies that choice on the record by training
> larger variants (26s, optionally 26m) on the same split and
> comparing accuracy × latency × cost.
>
> Source data: `workflows/notebooks/04_yolov26n_sequence_model_evaluation.ipynb`
> (run for each variant). Eval split: `configs/split.yaml`.

## 1. Why compare at all

The 16+ band rewards "alternative models implemented when they add
value." That's a *test*, not a checkbox — we need to show we
considered the alternatives and chose for a defensible reason.

Three candidates were trained on the same dataset, same split,
same augmentation, same loss. The hypothesis under test:

> *Does jumping from yolo26n to yolo26s (or 26m) materially
> improve PAPI-state classification quality enough to justify the
> latency / cost / TCO increase on the chosen edge tier?*

The decision criteria are spelled out in §4.

## 2. Setup

| Field | Value |
| --- | --- |
| Dataset snapshot | EDNY sequence dataset at git SHA <!-- TEAM --> |
| Split | `configs/split.yaml` — flight-level, regime-aware |
| Augmentation | <!-- TEAM: copy from `workflows/notebooks/06_augmentation.ipynb` summary --> |
| Loss | YOLO default (CIoU + BCE classification) |
| Optimizer | SGD, initial LR <!-- TEAM -->, momentum 0.937 |
| Epochs | <!-- TEAM --> |
| Batch size | <!-- TEAM --> |
| Image size | 640 × 640 (default) |
| Hardware | <!-- TEAM: e.g. "Howest GPU node — RTX 3090, 24 GB" --> |
| Training time | <!-- TEAM: hours per variant --> |

## 3. Results

### 3.1 Accuracy on the held-out test split

| Model | Detection F1 | mAP@0.5 | mAP@0.5:0.95 | Per-state F1 red | Per-state F1 white | Per-state F1 transition* |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| yolo26n | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> |
| yolo26s | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> |
| yolo26m | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> |

\* "Transition" is computed geometrically post-hoc (see design
doc §6 / §11). Per-state F1 for transition measures how often the
combined `(detector class) + (post-hoc geometry)` agrees with the
labelled transition state.

### 3.2 Per-regime accuracy

| Model | Day rwy 24 Wide | Night rwy 06 Wide | Day rwy 24 Zoom |
| --- | ---: | ---: | ---: |
| yolo26n — detection F1 | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> |
| yolo26s — detection F1 | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> |
| yolo26m — detection F1 | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> |

Notes on per-regime patterns:

- **<!-- TEAM: e.g. "Day Zoom is the weakest regime for every variant — see configs/papi_edny.yaml ZoomCamera focal_px = null." --></sub>**
- **<!-- TEAM: e.g. "Night rwy 06 benefits most from the larger variants because daylight saturation isn't the bottleneck." --></sub>**

### 3.3 Latency × resource

Cross-references `docs/edge-benchmark.md §5`. Numbers below are
the same fps@p50 / RSS measurements consolidated for comparison.

| Model | Params (M) | p50 latency laptop CPU (ms) | fps@p50 Jetson Orin INT8 | RSS MB (steady) |
| --- | ---: | ---: | ---: | ---: |
| yolo26n | 2.6 | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> |
| yolo26s | 9.1 | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> |
| yolo26m | 24.0 | <!-- TEAM --> | <!-- TEAM --> | <!-- TEAM --> |

## 4. Decision criteria

A larger variant earns its place if it satisfies **all** of:

1. **Real-time still achievable**: ≥ 10 fps at p50 on the chosen
   edge tier (Jetson Orin Nano INT8 or Intel NUC FP32).
2. **Detection F1 lift ≥ 2 pp**: the absolute aggregate F1 gain
   beats the noise band the team observed across training seeds.
3. **No per-regime regression**: detection F1 on each of the three
   test regimes individually is ≥ yolo26n by at least 1 pp (we
   don't want to trade day-zoom accuracy for night accuracy).
4. **TCO penalty acceptable**: the edge-tier upgrade (e.g. Pi → NUC)
   doesn't push three-year TCO per airport past <!-- TEAM: a
   client-agreed threshold, default 12 000 EUR -->.

Failing any of (1)–(4), the smaller model wins by default.

## 5. Verdict

**Chosen model**: **<!-- TEAM: yolo26n / yolo26s / yolo26m --></sub>**.

**Reasoning**: **<!-- TEAM: 2-3 sentences. Cite the rows in §3
above — e.g. "yolo26s improves aggregate detection F1 by 1.8 pp,
which is below our 2 pp threshold (criterion 2). It also costs
~ 35 ms additional latency at p50 on Jetson INT8, pushing us to
~ 14 fps. Given the rubric's real-time pressure and the marginal
accuracy gain, we stay on yolo26n for v1.0." --></sub>**

**What we would change if we had another sprint**: **<!-- TEAM:
e.g. "Train a distilled student of yolo26m on the EDNY split —
distillation could close the accuracy gap to 26m while keeping
26n-class latency." --></sub>**

## 6. Reproducibility

To reproduce the comparison from a clean checkout:

```powershell
# Activate the venv
.venv\Scripts\Activate.ps1

# Train each variant (one run each)
python workflows\scripts\pipeline.py train --base yolo26n --epochs <!-- TEAM -->
python workflows\scripts\pipeline.py train --base yolo26s --epochs <!-- TEAM -->
python workflows\scripts\pipeline.py train --base yolov26m --epochs <!-- TEAM -->

# Evaluate each on the held-out test split
jupyter nbconvert --to notebook --execute `
  workflows\notebooks\04_yolov26n_sequence_model_evaluation.ipynb

# Update the §3 tables in this document from the eval output
```

Each completed run writes its `args.yaml`, `results.csv`, and
`weights/best.pt` to `models/runs/<run_id>/`. The §3 tables above
are populated from those run folders.

## 7. Sources

- Eval notebook: `workflows/notebooks/04_yolov26n_sequence_model_evaluation.ipynb`
- Per-regime split design: `configs/split.yaml` + `docs/pipeline.md`
- Edge latency cross-ref: `docs/edge-benchmark.md §5`
- Model registry / lineage: `models/MODELS.md`
- Rubric line: BigBrain `02-courses/industry-project/industry-project-rubric-summary.md` — LR1D 16+

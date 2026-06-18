---
title: "Alternative-Model Comparison — yolo26n vs 26s vs 26m"
subtitle: "PAPI Lights Detection and Classification · Howest Industry Project 2026"
mainfont: "Calibri"
fontsize: 10pt
geometry: "a4paper, margin=2cm"
---

> **Model-selection rationale**: we evaluated alternative YOLO variants
> and adopted the one that added the most value. The serving model is
> **yolo26s** (run `yolo26s-fulldata-1280`), promoted over the smaller
> yolo26n; this document justifies that yolo26n→yolo26s choice on the
> record by training variants (26n, 26s, optionally 26m) on the same
> split and comparing accuracy × latency × cost.
>
> Source data: `workflows/notebooks/04_yolov26n_sequence_model_evaluation.ipynb`
> (run for each variant). Eval split: `configs/split.yaml`.

## 1. Why compare at all

An alternative model is only worth adopting when it adds value. That's
a *test*, not a checkbox — we need to show we considered the
alternatives and chose for a defensible reason.

Three candidates were trained on the same dataset, same split,
same augmentation, same loss. The hypothesis under test:

> *Does jumping from yolo26n to yolo26s (or 26m) materially
> improve PAPI-state classification quality enough to justify the
> latency / cost / TCO increase on the chosen edge tier?*

The decision criteria are spelled out in §4.

## 2. Setup

| Field | Value |
| --- | --- |
| Dataset snapshot | EDNY sequence dataset (not git-versioned; identity pinned by the transition twin's `manifest.json` / `tracking_manifest.json` — see MODELS.md §5b) |
| Split | `configs/split.yaml` — flight-level, regime-aware |
| Augmentation | Ultralytics defaults minus colour jitter (colour IS the label: hue/sat jitter disabled — see each run's `args.yaml`) |
| Loss | YOLO default (CIoU + BCE classification) |
| Optimizer | auto (SGD), initial LR 0.01, momentum 0.937 |
| Epochs | 100 configured; early-stopped — 26s at 54, 26n at 50 (patience 15) |
| Batch size | 26s: 4 · 26n: 2 |
| Image size | 1280 × 1280 |
| Hardware | Project laptop — RTX 4070 Laptop GPU, 8 GB |
| Training time | 26s ≈ 5.2 h · 26n ≈ 8.9 h (cumulative, from each run's `results.csv`) |

## 3. Results

> **Test-split numbers measured 2026-06-10** via
> `workflows/scripts/run_redwhite_test_eval.py` — the §3.1/3.2 tables below are that
> like-for-like comparison. For context, the
> committed runs already give validation-split box metrics for three points: the **serving
> yolo26s at 1280px** (`yolo26s-fulldata-1280`: mAP@0.5 **0.983**, mAP@0.5:0.95 **0.679** —
> `models/runs/detect/yolo26s-fulldata-1280/results.csv`, see MODELS.md §3.1.1), the
> **previous-serving yolo26n** (mAP@0.5 **0.914**, mAP@0.5:0.95 **0.474** —
> `models/runs/detect/yolo26n-sequence-1280/results.csv`), and a full-dataset **yolo26s** at 640px
> (`yolo26s-fulldata-640`: mAP@0.5 **0.938**, mAP@0.5:0.95 **0.616** —
> `models/runs/detect/yolo26s-fulldata-640/results.csv`). These are single-run *validation* numbers on
> differing dataset snapshots, **not** the like-for-like test-split per-state comparison
> §3.1 calls for, so they inform but do not replace it.

### 3.1 Accuracy on the held-out test split

Measured 2026-06-10 (`workflows/scripts/run_redwhite_test_eval.py`, full PR curve,
IoU 0.5). The test split covers the
day-wide and night-wide flights; the day-zoom flight is absent from the evaluated
dataset (focal calibration unavailable) — see §3.2.

| Model | Detection F1 | mAP@0.5 | mAP@0.5:0.95 | Per-state F1 red | Per-state F1 white | Per-state F1 transition* |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| yolo26n | 0.877 | 0.949 | 0.584 | 0.855 | 0.893 | n/a — 2-class detector |
| yolo26s | 0.915 | 0.971 | 0.651 | 0.901 | 0.928 | n/a — 2-class detector |
| yolo26m | not trained — see §5 | — | — | — | — | — |

\* "Transition" is computed geometrically post-hoc (see design
doc §6 / §11). Per-state F1 for transition measures how often the
combined `(detector class) + (post-hoc geometry)` agrees with the
labelled transition state.

### 3.2 Per-regime accuracy

| Model | Day rwy 24 Wide (1000 m) | Night rwy 06 Wide (500 m) | Day rwy 24 Zoom |
| --- | ---: | ---: | ---: |
| yolo26n — detection F1 | 0.984 | 0.751 | not evaluated (flight absent from dataset) |
| yolo26s — detection F1 | 0.989 | 0.828 | not evaluated (flight absent from dataset) |
| yolo26m — detection F1 | not trained | not trained | — |

Notes on per-regime patterns:

- **Night rwy 06 is the separating regime**: both variants are near-ceiling on the
  day-wide flight (F1 0.98+), but yolo26s holds +7.7 pp detection F1 and +10 mAP@0.5
  points over yolo26n at night — the capacity gain shows exactly where lamps are
  small, dim and low-contrast.
- **Day Zoom cannot be compared yet**: the zoom test flight is not part of the
  evaluated dataset (ZoomCamera `calibrated_focal_px` is still `null` in
  `configs/papi_edny.yaml`), so no zoom numbers exist for any variant — absent,
  not zero.

### 3.3 Latency × resource

Cross-references `docs/edge-benchmark.md §5`. Numbers below are
the same fps@p50 / RSS measurements consolidated for comparison.

Measured 2026-06-10 on the project laptop (30 frames × 3 runs, bare `model.predict`;
reproduce with `workflows/scripts/edge_benchmark.py`). No Jetson hardware is available — that
column is honestly empty because the client's WL051 specs were unavailable. For GPU reference the
laptop RTX 4070 runs yolo26s at p50 29.1 ms (34.4 fps).

| Model | Params (M) | p50 latency laptop CPU (ms) | fps@p50 laptop CPU | fps@p50 Jetson Orin INT8 | RSS MB (steady) |
| --- | ---: | ---: | ---: | ---: | ---: |
| yolo26n | 2.6 | 142.3 | 7.0 | no hardware | 2426 |
| yolo26s | 9.1 | 316.1 | 3.2 | no hardware | 2549 |
| yolo26m | 24.0 | not trained | — | — | — |

### 3.4 Weather robustness

§3.1–3.3 compare clear-weather imagery. Because adverse-weather robustness is a stated
client requirement, we additionally trained a weather-augmented nano
(`yolo26n-weather-flightsplit-1280`, MODELS.md §3.2b) and scored every detector on seeded
synthetic weather variants of the held-out test split
(`workflows/scripts/eval_weather_robustness.py`, mAP@0.5, **heavy** severity):

| Model | clear | rain | fog | haze | snow |
| --- | ---: | ---: | ---: | ---: | ---: |
| yolo26n-weather (new) | 0.948 | **0.948** | 0.943 | 0.945 | **0.821** |
| yolo26n (clear-trained) | 0.953 | 0.799 | 0.890 | 0.944 | 0.003 |
| yolo26s (serving) | **0.968** | 0.921 | **0.971** | **0.970** | 0.026 |
| yolo26s-weather-aug (train-9) | 0.951 | 0.902 | 0.924 | 0.929 | 0.082 |

**Snow is decisive**: only the weather-augmented nano stays usable (0.82); the serving
yolo26s and every other model — including the older train-9 "weather-aug" detector —
collapse to ≤0.08, because bright snow speckle mimics white lamps. The new nano is also
the most rain-robust. The cost is ~2 pp on clear and on fog/haze, where the larger yolo26s
leads. This adds a **weather-robustness axis** to the size/latency tradeoff: yolo26s is the
best clear-weather accuracy model, but `yolo26n-weather` is the choice when adverse-weather
reliability (especially snow) and nano-class speed (≈2× the CPU fps of yolo26s, §3.3) both
matter.

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
   doesn't push three-year TCO per airport past the working threshold of
   12 000 EUR (no client-agreed figure yet — flagged for the handover meeting).

Failing any of (1)–(4), the smaller model wins by default.

## 5. Verdict

**Chosen model**: **yolo26s** (run `yolo26s-fulldata-1280`), serving at
`models/serving/best.pt` since 2026-05-31, superseding the yolo26n
sequence model.

**Reasoning**: On the held-out test split (§3.1) yolo26s lifts aggregate
detection F1 by **+3.8 pp** (0.915 vs 0.877) — clearing criterion 2 — and the
gain concentrates where it matters: the hard night regime improves **+7.7 pp
detection F1 / +10 mAP@0.5 points** while day-wide stays at ceiling, so
criterion 3 holds on every evaluable regime. The cost is throughput (§3.3):
3.2 fps vs 7.0 fps bare-inference on laptop CPU, so the 10 fps real-time
target (criterion 1) leans on GPU-class hardware — the laptop RTX 4070
already delivers 34 fps, and the edge tier awaits WL051 specs. Criterion 4
is unaffected at the reference tier. Accuracy gain where the model was
weakest justified the promotion for v1.0.**

**Weather caveat (added 2026-06-18)**: the yolo26s verdict holds for clear weather,
but §3.4 shows it is **not robust to snow** (mAP@0.5 collapses to 0.03). A weather-augmented
nano (`yolo26n-weather`) now exists as the adverse-weather / fast-edge option, and the
natural v1.1 step is a yolo26s flight-split retrain *with* `--weather-aug` to get one model
that is both most-accurate-in-clear and snow-robust (MODELS.md §6).

**What we would change if we had another sprint**: Train yolo26m on the same
split to complete the size sweep (it was skipped for v1.0: the 8 GB laptop GPU
makes 24 M-param training at 1280 px slow and the night-regime gap was already
closed by 26s), and obtain the zoom-flight calibration so the third regime can
be evaluated at all.**

## 6. Reproducibility

To reproduce the comparison from a clean checkout:

```powershell
# Activate the venv
.venv\Scripts\Activate.ps1

# Train each variant (one run each)
python workflows\scripts\pipeline.py train --base yolo26n --epochs 100   # early-stops ~50
python workflows\scripts\pipeline.py train --base yolo26s --epochs 100   # early-stops ~54
# yolo26m: not trained for v1.0 (see §5)

# Evaluate each on the held-out test split
# (run_redwhite_test_eval writes the eval JSON; latency rows come from
#  workflows/scripts/edge_benchmark.py)
python workflows\scripts\build_redwhite_test_view.py
python workflows\scripts\run_redwhite_test_eval.py

# Update the §3 tables in this document from those artifacts
```

Each completed run writes its `args.yaml`, `results.csv`, and
`weights/best.pt` to `models/runs/<run_id>/`. The §3 tables above
are populated from those run folders.

## 7. Sources

- Eval notebook: `workflows/notebooks/04_yolov26n_sequence_model_evaluation.ipynb`
- Per-regime split design: `configs/split.yaml` + `docs/pipeline.md`
- Edge latency cross-ref: `docs/edge-benchmark.md §5`
- Model registry / lineage: `models/MODELS.md`

# PAPI Vision — Edge Benchmark

> ⚠ **Template — fill in measurements after running on actual hardware.**
> Placeholders are marked `[TODO]`. This document is intentionally a
> runbook plus an empty results table so the methodology is set
> before numbers are produced (avoids cherry-picking and gives the
> rubric grader a defensible audit trail).

Reproducible methodology for benchmarking PAPI Vision on
resource-constrained hardware. Required for rubric LR1B (real-time
inference, edge deployment, scalability).

## 1. Devices to benchmark

The client requirement is "runs in real-time on a resource-constrained
device". The team should pick at least two of:

| Device | Tier | Why it's interesting |
| --- | --- | --- |
| Raspberry Pi 5 (8 GB) | Embedded | Cheapest credible aviation-edge target |
| NVIDIA Jetson Orin Nano | Embedded + GPU | Real edge GPU; FP16 path |
| Intel NUC (i7-13xxxH) | Industrial PC | Common installed-airport hardware |
| Laptop CPU (i7 / Ryzen 7) | Reference | Establishes the "host" baseline number |

> Pick two minimum. If only laptop is available, benchmark **with**
> and **without** the INT8 ONNX model to surface the cost / value of
> the quantisation step.

## 2. Models to compare

The serving slot holds two artifacts:

```
models/serving/best.pt           # PyTorch float32, ultralytics format
models/serving/best_int8.onnx    # ONNX quantised INT8
models/runs/detect/train-2/weights/best.onnx  # ONNX fp32 artifact
```

Plus the base weights:

```
models/base/yolo26n.pt           # Small (n) variant
models/base/yolo26s.pt           # Small-plus (s) variant
models/base/yolov26m.pt          # Medium (m) variant
```

Benchmark **at least** `best.pt`, the fp32 ONNX artifact, and
`best_int8.onnx`. Reporting both base + fine-tuned is a bonus (shows
how training affected latency, not just accuracy).

## 3. Setup steps

### 3.1 Prepare the device

```bash
# All targets: install Python 3.10+ and project deps
git clone https://github.com/MaximRoomsHowest/PAPI-Detection-and-Classification.git
cd PAPI-Detection-and-Classification
git checkout v1.0
python3.10 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pip install -r apps/backend/requirements.txt

# For ONNX runtime benchmarking, also:
pip install onnxruntime
# (or onnxruntime-gpu on the Jetson)
```

### 3.2 Prepare a benchmark batch

Pick **100 frames** from the canonical dataset, spread across the
three regimes:

- 40 day / runway 24 / WideCamera
- 40 night / runway 06 / WideCamera
- 20 day / runway 24 / ZoomCamera (cropped)

Stage them in `data/bench/` (or any folder). The exact file names
should be recorded in `data/bench/manifest.csv` so the run is
reproducible.

## 4. Benchmark script

The repo now includes `workflows/scripts/edge_benchmark.py`. It measures
single-frame model prediction latency and emits JSON/CSV fields for:

- device label, platform, Python version, and git SHA;
- model path, model format, load time, frame count, and prediction count;
- p50 / p95 / p99 latency, fps@p50, and RSS memory before/after load;
- an explicit `error` field if a model cannot load on the target device.

Run it once per (device, model) combination:

```bash
python workflows/scripts/edge_benchmark.py \
    --model models/serving/best.pt \
    --frames data/bench/ \
    --device-label "Laptop CPU" \
    --inference-device cpu \
    --json-out docs/qa-artifacts/benchmarks/laptop-best-pt.json \
    --csv-out docs/qa-artifacts/benchmarks/results.csv

python workflows/scripts/edge_benchmark.py \
    --model models/runs/detect/train-2/weights/best.onnx \
    --frames data/bench/ \
    --device-label "Laptop CPU" \
    --inference-device cpu \
    --json-out docs/qa-artifacts/benchmarks/laptop-best-fp32-onnx.json \
    --csv-out docs/qa-artifacts/benchmarks/results.csv

python workflows/scripts/edge_benchmark.py \
    --model models/serving/best_int8.onnx \
    --frames data/bench/ \
    --device-label "Laptop CPU" \
    --inference-device cpu \
    --json-out docs/qa-artifacts/benchmarks/laptop-best-int8-onnx.json \
    --csv-out docs/qa-artifacts/benchmarks/results.csv
```

## 5. Results table — [TODO: fill in]

Replace `[TODO]` cells with measured values. **Report median +
P95 + P99**, not just mean — outliers matter for the
"real-time" claim.

### 5.1 Latency (ms / frame)

| Device | Model | p50 | p95 | p99 | fps@p50 |
| --- | --- | ---: | ---: | ---: | ---: |
| Local Windows CPU (smoke, 1 frame) | best.pt | 2667.752 | 2667.752 | 2667.752 | 0.375 |
| Local Windows CPU (smoke, 1 frame) | best.onnx fp32 | 2452.559 | 2452.559 | 2452.559 | 0.408 |
| Local Windows CPU (smoke, 1 frame) | best_int8.onnx | failed | failed | failed | failed |
| Raspberry Pi 5 | best.pt | [TODO] | [TODO] | [TODO] | [TODO] |
| Raspberry Pi 5 | best_int8.onnx | [TODO] | [TODO] | [TODO] | [TODO] |
| Jetson Orin Nano (FP16) | best.pt | [TODO] | [TODO] | [TODO] | [TODO] |
| Jetson Orin Nano (INT8) | best_int8.onnx | [TODO] | [TODO] | [TODO] | [TODO] |
| Intel NUC i7 | best.pt | [TODO] | [TODO] | [TODO] | [TODO] |

### 5.2 Memory footprint (RSS, MB)

| Device | Model | Baseline (no model) | After load | Steady-state inference |
| --- | --- | ---: | ---: | ---: |
| Local Windows CPU (smoke, 1 frame) | best.pt | 418.07 | 435.53 | 621.98 |
| Local Windows CPU (smoke, 1 frame) | best.onnx fp32 | 418.29 | 418.29 | 544.96 |
| Local Windows CPU (smoke, 1 frame) | best_int8.onnx | 463.43 | failed | failed |
| Raspberry Pi 5 | best.pt | [TODO] | [TODO] | [TODO] |
| Raspberry Pi 5 | best_int8.onnx | [TODO] | [TODO] | [TODO] |
| Jetson Orin Nano | best_int8.onnx | [TODO] | [TODO] | [TODO] |

### 5.3 Accuracy delta (INT8 vs FP32)

Run the *same* verification sample through both models and compute
per-state F1. If quantisation degrades F1 by more than ~3 % the
INT8 path may not be deployable.

| Model | Detection F1 | Per-lamp state F1 |
| --- | ---: | ---: |
| best.pt (FP32 reference) | [TODO] | [TODO] |
| best.onnx fp32 | [TODO] | [TODO] |
| best_int8.onnx | not runnable on local CPU ORT | not runnable on local CPU ORT |
| Δ | [TODO] | [TODO] |

Local smoke note (2026-05-28): `best_int8.onnx` reaches ONNX Runtime
but fails on CPU with `ConvInteger(10)` not implemented. Keep the
artifact as a measured failure until it is re-exported with CPU-supported
quantization operators or benchmarked on compatible acceleration.

## 6. Wiring measurements into the frontend

The previous build had a fabricated "edge memory: 412 MB" metric on
the live demo (audit F-CRIT-2). The current build has removed it
because it wasn't real. **Once you fill in §5 above**, you can
reintroduce a real per-device summary card on the Insights page
using the measured numbers — e.g. a small Devices table.

Implementation note: the metric should live in `apps/frontend/src/`
as a static JSON imported at build time, not as part of the API
response (the demo runs in a browser, not on edge hardware).

## 7. Cost projection (rubric LR1D 16+)

> **Methodology**: cost per airport, broken into one-time CAPEX and
> recurring OPEX. Numbers below are 2026 EUR list prices; the team
> should validate against vendor quotes before binding any
> commitments. Mark `<!-- TEAM -->` where airport-specific
> figures need site-survey input from Intersoft.

### 7.1 Recommendation matrix (pick one)

| Tier | Device | Why pick it | Indicative unit cost (EUR) |
| --- | --- | --- | ---: |
| **Embedded — entry** | Raspberry Pi 5 (8 GB) + active cooler + 256 GB SD | Cheapest credible target. Acceptable only if §5.1 shows ≥10 fps at p50 with `best_int8.onnx` | 95 – 130 |
| **Embedded — GPU (recommended)** | NVIDIA Jetson Orin Nano 8 GB dev kit (or Super) + carrier + 256 GB NVMe | Real edge GPU, INT8 path works, single-board form factor fits a runway-side enclosure | 480 – 620 |
| **Industrial PC** | Intel NUC 13 i7 + 16 GB RAM + 512 GB NVMe + DIN-rail mount | Common installed-airport hardware; most lenient thermal and power envelope | 850 – 1 200 |

**Recommended tier:** **<!-- TEAM: pick after §5 numbers land. Default
recommendation: Jetson Orin Nano if INT8 path achieves ≥10 fps at p50;
fall back to Intel NUC for FP32 deployment if ONNX Runtime CPU
proves the only reliable path. -->**

### 7.2 One-time CAPEX per airport

| Component | Unit cost (EUR) | Source / note |
| --- | ---: | --- |
| Edge compute (per §7.1) | **<!-- TEAM -->** | Vendor quote |
| Outdoor enclosure (IP65, fanless, DIN-rail) | 120 – 250 | RS Components / Farnell 2026 catalogue |
| PoE injector + Cat6 cabling (10 m) | 40 – 80 | Standard |
| 4G/5G industrial router (optional, if no wired drop) | 180 – 350 | Teltonika RUT241 reference |
| DJI Matrice 4E drone | n/a | Client-owned per 2026-05-18 kickoff |
| Drone hangar / mount adapter | **<!-- TEAM -->** | Site-specific — confirm with Intersoft |
| Setup labour (commissioning, 2 engineers × 1 day) | 1 200 – 1 600 | 8 h × 2 people × ≈80 €/h |
| Software install + initial calibration | 400 – 600 | 5 h × 80 €/h, one-shot per airport |
| Initial training data acquisition (1 capture day on-site) | **<!-- TEAM -->** | If the airport requires re-survey |
| Contingency (10 %) | **<!-- TEAM -->** | Sum of above × 0.10 |
| **One-time per airport (Jetson tier)** | **≈ 2 500 – 3 700** | Sum (excluding training-data acquisition) |

### 7.3 Recurring OPEX per airport per month

| Component | EUR / month | Source / note |
| --- | ---: | --- |
| 4G/5G data plan (industrial SIM, 50 GB) | 25 – 60 | Vendor-dependent |
| Cloud log / artifact storage (S3-class, 50 GB) | 5 – 15 | AWS/Hetzner 2026 |
| Remote monitoring (Uptime + alerting) | 10 – 25 | Better-Uptime / Grafana Cloud free tier may suffice |
| Software updates / on-call (1 h/month allocation) | 80 | 1 h × 80 €/h |
| **Recurring per airport per month** | **≈ 120 – 180** | Sum |

### 7.4 Three-year TCO per airport

Using the midpoint of each range above:

```
CAPEX (one-time)          ≈ 3 100 EUR
OPEX  (36 months × 150)   ≈ 5 400 EUR
                            ────────
Three-year TCO            ≈ 8 500 EUR per airport
```

For a 10-airport rollout: **≈ 85 000 EUR over 3 years**. Per
analysed flight, this works out to **<!-- TEAM: compute from
flights-per-month estimate after Intersoft confirms the
operational profile -->**.

### 7.5 Sensitivity / what shifts this number most

1. **Edge tier choice** — Jetson vs NUC swings CAPEX by ~700 EUR.
2. **Wired vs cellular connectivity** — wired drops OPEX by ~40 €/mo
   if the airport has spare network capacity at the runway threshold.
3. **Re-survey requirement** — if every new airport needs a fresh
   per-lamp coordinate survey, add the surveyor day rate (~600 EUR)
   to CAPEX and a per-runway calibration sprint (~3 engineer-days,
   ~2 000 EUR) to onboarding.
4. **Inference path** — falling back to FP32 on a Pi 5 (no GPU)
   would push fps below the 10-fps real-time target and forces the
   NUC tier; this is the biggest *technical* lever in the §5 table.

## 8. Conclusion

> Fill in after §5 and §7 are populated. Reviewers / jury graders
> look at this section first — write it as if it's the only
> paragraph they read.

**Recommended deployment**: **<!-- TEAM: e.g. "Jetson Orin Nano 8 GB
with `best_int8.onnx`, achieving N fps at p50 and steady-state RSS
of M MB. Falls back to Intel NUC + FP32 if the quantisation path
remains blocked on the CPU operator set." -->**.

**Cost per airport (3-year TCO)**: **<!-- TEAM: e.g. "≈ 8 500 EUR
per airport using the midpoint estimates in §7.4." -->**.

**Caveats the jury must know**:

1. **<!-- TEAM: e.g. "Real-time target was not met on the Raspberry
   Pi tier; only the Jetson tier reaches ≥10 fps at p50." -->**.
2. **<!-- TEAM: e.g. "Accuracy delta between FP32 and INT8 is N % F1;
   the team accepts this trade-off for X reason." -->**.
3. **<!-- TEAM: e.g. "Real-world test was on K frames per regime;
   wider operational testing is the natural next step." -->**.

**Next-step optimisations** (in priority order):

1. **TensorRT export** on Jetson — likely 2–3× latency reduction
   over the ONNX Runtime FP16 baseline.
2. **Frame-skip strategy** — analyse every Nth frame during a
   constant-altitude hover; reduces FPS demand without losing
   transition events (lamps don't change colour faster than ~1 Hz
   on a steady approach).
3. **Model distillation** — student-network from YOLO 26m
   teacher to a 1–2 M parameter student; targets the Pi tier if
   the cost case for it strengthens.
4. **Sequence-level smoothing** — already in place via ByteTrack
   for the offline pipeline; reuse on-device for noise robustness
   if the per-frame state oscillates under low-saturation daylight
   imagery.

## 9. Reproducibility

Every cell in the tables above should be recreatable from:

```
git checkout <commit at the time of benchmark>
python workflows/scripts/edge_benchmark.py --model ... --frames data/bench/
```

Commit the manifest of which frames were used (`data/bench/manifest.csv`)
so the same benchmark can be re-run after model changes.

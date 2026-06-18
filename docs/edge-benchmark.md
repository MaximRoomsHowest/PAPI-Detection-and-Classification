# PAPI Lights Detection and Classification — Edge Benchmark

This document records the benchmark results available at final
delivery. It does not invent numbers for hardware the team did not
receive.

## 1. Goal

The client requirement is that the system can run in real time on
resource-constrained hardware. For this project, the team measured:

- laptop CPU inference;
- laptop GPU inference;
- CPU backend options for a 2-CPU cloud budget.

Raspberry Pi, Jetson, Intel NUC, and Intersoft WL051 measurements were
not available because the team did not have that hardware.

## 2. Models and Backends

| Artifact | Purpose | Status |
|---|---|---|
| `models/serving/best.pt` | Main PyTorch serving model, yolo26s | Used |
| `models/runs/detect/yolo26n-sequence-1280/.../best.pt` | Smaller yolo26n comparison model | Measured |
| `best.onnx` | FP32 ONNX export | Accuracy parity checked |
| `best_openvino_model` | FP32 OpenVINO export | Recommended CPU backend |
| INT8 ONNX export | Retired export | Not shipped; the old artifact was not usable on CPU |

## 3. Laptop Inference Results

Measured on 2026-06-10 with `workflows/scripts/edge_benchmark.py`
(30 frames x 3 runs, warm `model.predict`).

| Device | Model | p50 ms | p95 ms | p99 ms | fps@p50 |
|---|---|---:|---:|---:|---:|
| Project laptop CPU | yolo26s `best.pt` | 316.1 | 414.2 | 455.4 | 3.16 |
| Project laptop CPU | yolo26n `best.pt` | 142.3 | 214.7 | 220.9 | 7.03 |
| Project laptop RTX 4070 | yolo26s `best.pt` | 29.1 | 35.6 | 36.4 | 34.4 |

Reading:

- GPU inference meets the 10 fps real-time target.
- CPU-only inference does not meet 10 fps at 1280 px.
- yolo26s is more accurate than yolo26n, but slower on CPU.

## 4. Memory Results

| Device | Model | Baseline MB | After load MB | Steady-state MB |
|---|---|---:|---:|---:|
| Project laptop CPU | yolo26s `best.pt` | 2235.5 | 2289.1 | 2548.5 |
| Project laptop CPU | yolo26n `best.pt` | 2235.5 | 2252.6 | 2426.1 |
| Project laptop RTX 4070 | yolo26s `best.pt` | 2235.3 | 2288.8 | 2930.2 |

The high baseline comes from the development environment and its
CUDA-enabled torch build. Compare deltas within the same row.

## 5. CPU Backend Comparison

Measured on 2026-06-16 with a 2-thread CPU budget over the 18-frame
`data/eval/builtin-detector-redwhite` set.

| Backend | p50 ms | p95 ms | p99 ms | fps@p50 | Result |
|---|---:|---:|---:|---:|---|
| PyTorch `best.pt` | 240.0 | 262.9 | 298.9 | 4.17 | Baseline |
| ONNX Runtime FP32 | 548.3 | 589.1 | 612.6 | 1.82 | Slower |
| OpenVINO FP32 | 157.3 | 159.9 | 540.8 | 6.36 | Best CPU backend |
| RTX 4070 PyTorch | 21.7 | 38.8 | n/a | 46.2 | GPU reference |

OpenVINO and ONNX matched the PyTorch detections on the checked set:
0 box-count mismatches, 0 class mismatches, and maximum confidence drift
0.0377.

Decision: use OpenVINO as the CPU backend when available. Keep
`best.pt` as the GPU and universal fallback path.

## 6. Hardware Not Tested

| Target | Status | Why |
|---|---|---|
| Raspberry Pi 5 | Not tested | Hardware unavailable |
| Jetson Orin Nano | Not tested | Hardware unavailable |
| Intel NUC | Not tested | Hardware unavailable |
| Intersoft WL051 workstation | Not tested | Specs/hardware unavailable during the project |

These rows should be measured by Intersoft before choosing the final
deployment target.

## 7. Deployment Recommendation

For this delivery:

- Use GPU hardware when real-time video speed is required.
- Use OpenVINO on CPU when GPU hardware is not available.
- Do not use the retired INT8 ONNX path for CPU deployment; it is not shipped
  in the lean handover package.
- Re-test on Intersoft WL051 before making a final production hardware
  decision.

## 8. Cost Projection

The team used a simple planning estimate for a Jetson-style edge
deployment:

| Cost area | Estimate |
|---|---:|
| One-time edge setup per airport | EUR 2,500-3,700 |
| Monthly operating cost per airport | EUR 120-180 |
| Three-year TCO per airport | about EUR 8,500 |

This is a planning estimate, not a quote. It excludes site-specific
survey work and any Intersoft procurement discounts.

## 9. Reproducibility

Benchmark command pattern:

```bash
python workflows/scripts/edge_benchmark.py \
  --model models/serving/best.pt \
  --frames data/bench/ \
  --device-label "Laptop CPU" \
  --inference-device cpu \
  --json-out models/runs/experiments/benchmarks/local-best-pt.json \
  --csv-out models/runs/experiments/benchmarks/results.csv
```

CPU backend comparison:

```bash
python workflows/scripts/backend_bench.py --threads 2 --device cpu
```

Keep the frame manifest with the benchmark output so future runs can be
compared against the same input set.

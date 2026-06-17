# PAPI Detection & Classification — Final Report of Results

**Project**: PAPI Lights Detection and Classification — Howest Industry Project 2025–26, for
Intersoft Electronics Services BV.
**Date**: 2026-06-10 (final handover 2026-06-19).
**System**: FastAPI backend + React frontend + YOLO detection models, deployable via Docker
Compose. Source layout and architecture: [architecture-overview.md](architecture-overview.md).

This is the single-page summary of what was built, how well it works (with every number traced
to a committed artifact), and what its honest limitations are. Detailed documents are linked
throughout.

---

## 1. What the system does

A drone flies the approach; the system answers three questions per image or video:

1. **Where are the PAPI lamps?** — a YOLO detector (`yolo26s-fulldata-1280`, serving slot
   `models/serving/best.pt`) finds each lamp as a red or white box.
2. **What is the glidepath state?** — the exact white-count lookup
   (`apps/backend/app/services/state.py`): 4W far-too-high · 3W1R too-high · 2W2R correct ·
   1W3R too-low · 4R far-too-low, plus `transition` and `unknown` (<4 lamps → per-lamp
   "obscured" rather than an invented verdict).
3. **Which lamp changed colour, and at what angle?** — per-lamp red↔white transitions from
   ByteTrack temporal tracking (default), each stamped with the WGS-84 ENU elevation angle
   (validated to ±0.02° against the client's tool) when telemetry is available. A learned
   3-class transition model is selectable as an alternative method (§4).

Real-time and offline paths share one inference core: single image, video upload, and
folder→video sequence analysis, served by `/api/analyze*` with a model registry
(`models/serving/models.json`, `GET /api/models`) that lets the operator pick the serving
detector per analysis.

## 2. Results — detection and 5-state classification

Training/validation metrics come from the committed run artifacts; held-out test metrics from
the flight-level test split (`configs/split.yaml` — no flight appears in two splits, so no
near-identical-frame leakage).

**Validation split** (`models/runs/detect/yolo26s-fulldata-1280/results.csv`, MODELS.md §3.1.1):
precision 0.948 · recall 0.937 · mAP@0.5 0.983 · mAP@0.5:0.95 0.679.

**Held-out test split** (harness: `workflows/scripts/run_redwhite_test_eval.py`,
full PR curve, IoU 0.5): see MODELS.md §3.1.2
for the per-regime table. The test split covers the 1000 m day-wide and 500 m night-wide
flights; the day-zoom test flight is not part of the evaluated dataset (zoom-camera focal
calibration pending from the client), so zoom-regime numbers are reported as absent — not zero
and not invented.

5-state classification is a deterministic lookup over the per-lamp colours, so state accuracy
follows red/white detection accuracy directly; `unknown` is returned rather than guessing when
fewer than 4 lamps are confidently detected.

## 3. Results — per-lamp transition recognition

Two methods ship, selectable per analysis:

- **Temporal tracking (default)** — red↔white flips on stable ByteTrack identities.
  Robust in production; head-to-head F1 0.278 on the pre-cleanup test set.
- **Learned 3-class model** (`transition3class-yolo26s-1280`, opt-in via the model selector) —
  after the 2026-06-09 label cleanup (487 → 250 transition boxes; ~49% of the old labels were
  stable-colour mislabels, removed by a colour-verdict gate) the retrained model hallucinates
  almost no transitions on stable lamps (false transitions 53 → 1, ~98% cut) but is
  recall-starved on the tiny test class. Full-PR-curve test metrics: red F1 0.80
  (support 765) · white F1 0.73 (support 625) · **transition F1 0.10, recall 2/6 (support 6)**.

**Decision on record**: temporal tracking stays the default; the learned model needs label
*quantity* (more verified flips), not more cleaning, before promotion.
The 6-box test support means per-class transition numbers carry very wide uncertainty — stated
here rather than hidden.

## 4. Honest framing: multi-task architecture

The brief asks for detection + classification + transition recognition "in a single
architecture". What ships is a **staged pipeline**, deliberately: one detector feeds an exact
state lookup and a temporal transition tracker. The stages are individually testable, the rare
transition class cannot starve detection training, and every verdict is explainable
(box → colour count → flip). The learned 3-class model is the measured step toward a single
multi-task net — and its current transition recall is the evidence for why the pipeline
remains the deliverable today. A true multi-head architecture stays on the roadmap with the
data-collection effort it requires.

## 5. Real-time and edge deployment

- Measured 2026-06-10 (bare warm inference at 1280 px, 30 frames × 3 runs; reproduce with
  `workflows/scripts/edge_benchmark.py`): laptop CPU p50 — yolo26s **316 ms (3.2 fps)**, yolo26n
  **142 ms (7.0 fps)**; laptop **RTX 4070 — 29 ms (34 fps)**. The full serialized request
  pipeline (decode → detect → overlay → artifact write) is slower — the historically quoted
  ~0.4 fps end-to-end CPU figure remains the honest serving number for CPU-only deployments.
- The 10 fps real-time target is therefore met on GPU-class hardware with margin and is not
  met CPU-only at 1280 px. The client workstation (WL051) specs are still pending, so edge
  numbers beyond the laptop reference are honestly absent. Methodology and runbook are ready
  (`docs/edge-benchmark.md`, `workflows/scripts/edge_benchmark.py`).
- INT8 ONNX status: see MODELS.md §3.2.1 (the previous export came from the retired yolo26n
  and does not run on CPU onnxruntime).

## 6. Domain adaptation

Training data is a **single airport** (EDNY Friedrichshafen, two runways, three regimes).
There is no cross-airport evaluation — generalisation to unseen airports is **untested**, and
the system is honest about it (`docs/data-card.md`). The geometry layer is already per-airport
(`configs/papi_*.yaml` + the add-runway API); the model is not. Roadmap: collect a small
labelled sample at a second airport → zero-shot eval with the EDNY model → fine-tune if the
F1 drop exceeds ~5 pp.

## 7. Reproducibility

- **Training**: Ultralytics args committed per run (`models/runs/**/args.yaml`):
  yolo26s-fulldata-1280 — seed 0, deterministic, imgsz 1280, batch 4, 54 epochs (~5.2 h);
  yolo26n-sequence-1280 — seed 42, deterministic, imgsz 1280, batch 2, 50 epochs (~8.9 h).
  Both on the project laptop's RTX 4070 (8 GB).
- **Split**: flight-level, committed (`configs/split.yaml`); QA gate
  (`workflows/scripts/qa_transition_dataset.py`) hard-fails on split leakage.
- **Evaluation**: every number above names its committed harness and artifact; the 2-class
  test view is rebuilt deterministically by `workflows/scripts/build_redwhite_test_view.py`.
- **Dataset**: raw flights are not git-versioned (size); identity is pinned by the twin's
  `manifest.json` + `tracking_manifest.json` and the label-gate audit trail
  (`verification_log.csv`, 487→250 with per-box decisions).
- **Serving**: model provenance via `/api/model` (load-time SHA-256, training run, val
  metrics); `models/serving/model_card.json` is generated, not hand-typed
  (`workflows/scripts/populate_model_metrics.py`).

## 8. Known limitations and open items

| Item | Status |
| --- | --- |
| Day-zoom regime | Not evaluated (flight absent from twin; `calibrated_focal_px` pending from client) |
| Edge hardware numbers | Pending WL051 specs; laptop reference only |
| Transition-model recall | 2/6 at full PR curve; needs label quantity (CVAT pass) before promotion |
| Cross-airport generalisation | Untested; roadmap above |
| Rwy-06 commissioned set-angles | Pending from client (FAA defaults in config; flagged per analysis) |
| Lamp↔set-angle binding | Config order does not match the data's empirical angles; transitions.csv is authoritative |

Everything in this report is reproducible from the repo; nothing here is estimated or
extrapolated beyond what the named artifacts contain.

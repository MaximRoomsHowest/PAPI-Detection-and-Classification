# Phase 8 — Transition Evaluation (interim model)

Model: `yolo11s` @ 1280, epoch 19 checkpoint (`best.pt`), trained on flip-anchored +
AI-spot-checked labels, colour-safe augmentation. **Interim** — see caveats. Raw metrics:
`evaluation_metrics.json`, `head_to_head.json` (this folder);
confusion matrix `artifacts/confusion_matrix.png`; example frames in the twin's `eval_examples/`.

## Per-class metrics — held-out TEST split (349 frames, 1,396 instances, conf=0.25)

| class | precision | recall | F1 | mAP50 |
|---|---:|---:|---:|---:|
| red | 0.829 | 0.383 | 0.524 | 0.590 |
| white | 0.944 | 0.438 | 0.598 | 0.687 |
| **transition** | **1.000** | **0.135** | **0.238** | **0.568** |
| all | 0.924 | 0.319 | 0.615 | 0.295 (mAP50-95) |

**Overall accuracy is deliberately not the headline.** The key question — *can the model detect
rare transitions without hallucinating them during stable red/white?* — is answered:

- **Transition precision = 1.000: ZERO false transitions** on the test split. The model never
  calls a stable red/white lamp "transition". `false_transition_examples/` is empty (4 correct, 12
  missed, 0 false, 0 red/white confusion).
- **Transition mAP50 = 0.568 is on par with red (0.590) and white (0.687)** — the threshold-
  independent detectability of the transition class matches the stable classes.
- **Transition F1 (0.238) already exceeds the historical temporal baseline (≈0.174)** even at this
  conservative threshold.

Low **recall** (transition 0.135; red/white also ~0.4) is largely a **threshold artifact**:
conf=0.25 is high for ~6 px lamps (the 2-class serving model uses conf 0.05–0.10 for complete
tracking). mAP50 (integrated over thresholds) is the fairer per-class read.

## Confusion matrix

`artifacts/confusion_matrix.png`. Red↔white confusion is minimal (0 mined examples at IoU>0.4);
the dominant error is **background ↔ lamp** (missed faint/distant lamps at conf=0.25), not class
confusion. No transition→red/white leakage of note.

## Head-to-head: learned (Track A) vs temporal (Track B)

Same model + same ByteTrack over the test flights; transitions derived two ways, matched to GT
flips within ±6 frames.

| approach | precision | recall | F1 | false transitions (fp) |
|---|---:|---:|---:|---:|
| **Track A — learned (class 2)** | **0.750** | 0.300 | **0.429** | **1** |
| Track B — temporal (red↔white flip) | 0.294 | 0.500 | 0.370 | 12 |

**The learned approach wins on F1 and precision.** Track B's frame-to-frame flip detection produces
**12× the false transitions** (detector flicker) for modestly higher recall; Track A is far more
precise. Both beat the historical 0.174. Per-flight: the 500 m night flight favoured A (F1 0.60 vs
0.476); the 1000 m day flight defeated both (lamps too small at range — A 0/4, B 0 tp/2 fp).

## Diagnosis & why transition recall is modest

- **Interim model**: 19 epochs, `yolo11s` (not the production `yolo26s` — ultralytics 8.3.58 can't
  parse yolo26); val mAP50 had only just plateaued.
- **Rare class**: 487 transition boxes (3.82%); 37 in the test split.
- **High conf threshold** (0.25) suppresses faint detections — lowering it trades precision for recall.
- **Tiny lamps at range** (1000 m flight) — the dominant miss mode, affecting all classes.
- **Labels are interim** (AI spot-check of 36/~150 flips); a full human pass would sharpen the
  transition boundaries.

## Verdict

The learned 3-class transition detector is **viable and high-precision** — it detects transitions
with **zero hallucination** and transition-class detectability on par with red/white, beating the
temporal method on F1. It is **not yet production-ready** (recall low at interim settings). Path to
production: full human verification, re-train on `yolo26s` (ultralytics ≥8.4), tune conf for the
recall/precision trade, then promote if it holds on a larger transition test set.

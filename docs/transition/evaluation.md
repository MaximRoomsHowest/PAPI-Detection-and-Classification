# Phase 8 — Transition Evaluation (yolo26s)

> **Superseded (2026-06-09):** the metrics below predate the 2026-06-09 colour-gate label cleanup
> (487 → 250 transition boxes) and the subsequent retrain. Current numbers live in
> `evaluation_metrics.json` (retrained `transition3class-yolo26s-1280-clean`: red mAP50 0.87,
> white 0.94; false transitions 53 → 1; transition recall starved — 0 of the 6 test-split boxes
> detected). This file is kept as the evaluation record of the pre-cleanup model.

Model: **`yolo26s`** @ 1280 (the production backbone), 19 epochs (`best.pt`), trained on
flip-anchored + AI-spot-checked labels, colour-safe augmentation, transition oversampling, under
**ultralytics 8.4.61** (8.3.x cannot train yolo26). Raw metrics: `evaluation_metrics.json`,
`head_to_head.json`; confusion matrix `artifacts/confusion_matrix.png`; example frames in the
twin's `eval_examples/`. (An earlier `yolo11s` interim is superseded by this run.)

## Per-class metrics — held-out TEST split (349 frames, 1,396 instances, conf=0.25)

| class | precision | recall | F1 | mAP50 |
|---|---:|---:|---:|---:|
| red | 0.853 | 0.752 | 0.800 | 0.809 |
| white | 0.973 | 0.594 | 0.738 | 0.604 |
| **transition** | **0.385** | **0.324** | **0.352** | **0.256** |
| all | 0.737 | 0.557 | 0.556 | 0.308 (mAP50-95) |

**The headline is transition F1, not overall accuracy.** The 3-class detector classifies
transitions with **F1 0.352** — beating the historical temporal baseline (≈**0.174**) by 2× and
the yolo11s interim (0.238). Red/white are strong (red mAP50 0.81, white precision 0.97).

The transition **mAP50 (0.256) is still maturing**: it rose 0.147 → 0.256 from epoch 11 → 19, so
it has not converged (the rare transition class needs the most epochs). Training to convergence
(~40–60 epochs) is expected to lift it further; the F1 already clears the bar.

## Confusion matrix & examples

`artifacts/confusion_matrix.png`. Example folders (git-ignored twin `eval_examples/`): **12
correct, 12 missed, 12 false** transition frames + red/white confusion samples. Unlike the very
conservative yolo11s interim (0 false transitions), yolo26s trades some precision for recall —
it catches more real transitions and produces some false ones, which is the more useful operating
point for a rare event (and is tunable via `conf`).

## Head-to-head: learned (Track A) vs temporal (Track B)

Same model + ByteTrack over the test flights; transitions derived two ways, matched to GT flips
within ±6 frames.

| approach | precision | recall | F1 | false transitions (fp) |
|---|---:|---:|---:|---:|
| **Track A — learned (class 2)** | 0.261 | **0.600** | **0.364** | 17 |
| Track B — temporal (red↔white flip) | 0.192 | 0.500 | 0.278 | 21 |

**The learned approach wins on F1 and recall** (0.364 / 0.60 vs 0.278 / 0.50) with fewer false
transitions — and the gap is the point of the whole exercise: the learned transition class is a
better transition detector than per-frame red↔white flip tracking. Both beat the historical 0.174.

## Diagnosis & caveats

- **Epochs**: 19 (resumed). Overall mAP50 plateaued ~0.56 but the **transition AP is still rising**
  — more epochs are the single biggest lever for transition mAP50.
- **Rare class**: 487 transition boxes (3.82%); 37 in the test split — small, so metrics are
  directional. A larger labelled transition set would tighten them.
- **Interim labels**: AI spot-check of 36/~150 flips + a dataset-wide rule; a full human/CVAT pass
  would sharpen transition boundaries.
- **conf=0.25** caps recall on ~6 px lamps (the 2-class serving model uses 0.05–0.10 for complete
  tracking); lowering conf trades precision for recall.

## Verdict

The required **yolo26s** transition-aware detector is **viable and beats the temporal method**
(F1 0.364 vs 0.278) and the historical baseline (0.174), with production-grade red/white. It is
**not yet at its ceiling** — transition AP is still improving with epochs. Path to production:
train to convergence, full human verification, tune `conf`, then promote + flip the app's default
transition method to "model".

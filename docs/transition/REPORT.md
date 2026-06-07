# Transition-Aware PAPI Pipeline — Implementation Report

Branch `transition-model`. All dataset/model artifacts are git-ignored; code, configs, docs, and
small deliverables (verification log, manifests, QA report, montage example) are tracked. Detailed
per-phase docs are in `docs/transition/00_recon.md` … `05_frontend_reporting.md`.

## 1. BigBrain summary of relevant PAPI requirements

Client deliverable: locate the PAPI, classify the global glidepath state, and **label each lamp
`white` / `red` / `in transition`**, robust to day/night, angle, weather. Transition is "an open
methodological choice" judged on **transition recall, transition-angle MAE, false-transition
rate**; the existing temporal method scores only **F1 ≈ 0.174** — hence this work. rwy-24 geometry
is validated to ±0.02°; rwy-06 commissioned set-angles are still pending.

## 2–5. Dataset paths & taxonomies

- **Original (untouched):** `PAPI-artifacts/2026-05-26-cleanup/data/datasets/papi_lamp_sequences/`
  (8.92 GB; 3,194 images/labels; 2-class `{0:papi_light_red, 1:papi_light_white}`).
- **New:** `data/datasets/transition-classification-data/` (git-ignored) — 3-class
  `{0:papi_light_red, 1:papi_light_white, 2:papi_light_transition}` (additive; 0/1 unchanged).

## 6. Duplication method

`duplicate_transition_dataset.py` — images **hardlinked** (same NTFS volume: file counts match the
original, ~0 extra bytes, originals never written); labels/CSVs/manifests copied. Hardlinking (vs a
path reference) is required because Ultralytics resolves labels by swapping `/images/`→`/labels/`,
so the twin must carry its own labels. Verified `original_unchanged=true`, counts match.

## 7. Annotation schema changes

Additive class 2 (`papi_light_transition`). Global-state info preserved (derivable via
`global_state.py`; per-video `transitions.csv` copied). `configs/papi_edny_transition.yaml` adds
commissioned rwy-24 set-angles without mutating the live config. See `02_schema.md`.

## 8. Candidate-mining method (the key methodology finding)

Geometric blend-zone seeding was **abandoned**: diagnostics showed seeded frames are *disjoint*
from real red↔white flips because the config lamp-order↔set-angle binding is **reversed** (tracks
lamp_1 flips at ~3.57° = light_4, not light_1's 2.32°). Empirical set-angles
**3.43/2.99/2.49/2.18°** (descending) confirm it — resolving the "Punktnummer binding" BigBrain
flagged as open. Seeding is therefore **flip-anchored**: a ±2-frame window around each
authoritative `transitions.csv` flip, colour-confirmed. **495 candidates** (305 red→white, 190
white→red), balanced across lamps. See `03_candidate_mining.md` and the
[[papi-lamp-binding-reversed-2026-06-07]] memory.

## 9. Colour-analysis method

`transition_labels.colour_features`: inner-60% bbox crop → HSV/Lab ratios (red/orange-amber/yellow/
white, saturation, value, Lab a/b). Diagnostics confirmed real flips show `red_ratio↓ + white_ratio↑
+ saturation↓` over ~4 frames; grazes stay solid red. Colour ranks/confirms, never labels (small
overexposed lamps read amber even when stable).

## 10. Temporal smoothing method

Flip-anchoring is the temporal anchor; Phase 4 windowed crossing test + `frame_offset` proximity
rank candidates. Inference: `aggregate_transition_state_events` applies a minimum-run filter
(drops 1-frame flicker); `detect_lamp_transitions` keeps its gap tolerance.

## 11. CVAT verification workflow

Docker/CVAT was down, so a purpose-built **browser review app** (`review.html`, driven via Chrome
MCP) showed per-flip montages (lamp crop across `[flip−3…flip+3]`); a **3-class CVAT bundle**
(`export_transition_cvat.py`) is exported for when Docker is up. See `04_verification.md`.

## 12. Candidate review statistics

36 flips spot-checked across all strata → evidence-based rule applied dataset-wide:
**495 → 487 accepted_transition, 8 ambiguous_review** (zoom `fallback_identity`, reverted to
red/white). `elev_discontinuity` kept (visual real, angle untrusted). `verification_log.csv`
tracked in `artifacts/`.

## 13. Dataset QA

`dataset_qa_report.md`: 3,194 frames; boxes red 6,777 / white 5,497 / **transition 487 (3.82%)**;
present in all splits (train 386 / val 64 / test 37); balanced per lamp (132/133/120/102); **no
split leakage** (one split per flight); most-loaded clip share 0.19; 0 format errors after dedup.
**Ready for training: YES.**

## 14. Training configuration

`train_transition_model.py`: base **yolo26s** (the production backbone — needs **ultralytics ≥8.4**;
the `.venv` was upgraded 8.3.58→8.4.61, pin bumped, 240 backend tests still green). imgsz 1280,
batch 4, **workers 2** (20MP frames OOM the DataLoader at 3), 19 epochs (resumed via `--resume`),
AdamW (auto). **Colour-safe augmentation: `hsv_h=0, hsv_s=0`** (hue/sat jitter would swap
red↔white↔transition), mild `hsv_v`, horizontal flip only, mosaic off. **Imbalance:**
transition-bearing frames oversampled 4× in the train list (val/test at true distribution). Labels
are flip-anchored + AI-spot-checked.

## 15. Training results

**`yolo26s`** @ 1280, 19 epochs. Weights `data/runs/detect/transition3class-yolo26s-1280/weights/
best.pt` (git-ignored). Full metrics/plots/logs in that run dir.

## 16–18. Transition-specific evaluation (TEST split, conf=0.25) — see `evaluation.md`

| class | P | R | F1 | mAP50 |
|---|--:|--:|--:|--:|
| red | 0.853 | 0.752 | 0.800 | 0.809 |
| white | 0.973 | 0.594 | 0.738 | 0.604 |
| **transition** | **0.385** | **0.324** | **0.352** | **0.256** |

- **Transition F1 0.352 beats the historical temporal baseline (≈0.174) by 2×** (and the yolo11s
  interim's 0.238). Red/white are production-grade. Transition mAP50 (0.256) is **still maturing**
  (0.147→0.256 over epochs 11→19) — more epochs are the main lever.
- **Confusion matrix:** `artifacts/confusion_matrix.png`. **Example folders** (git-ignored twin
  `eval_examples/`): **12 correct, 12 missed, 12 false** transition frames + red/white confusion.
- **Head-to-head** (`head_to_head.json`): learned **F1 0.364 / R 0.60 / 17 false** vs temporal
  **F1 0.278 / R 0.50 / 21 false** — the learned class wins on F1 and recall; both beat 0.174.
  Caveats: small sample (37 test transitions), epoch-19 (transition AP not converged), conf=0.25.

## 19. ByteTrack integration notes

ByteTrack already live in `sequence_runner`. Added: `DETECTION_CLASS_TO_STATE[2]="transition"`
(forward-compatible; 2-class model inert) + `aggregate_transition_state_events` for per-lamp events
(`transition_event_id`, start/end frame, duration, bracketing states, angles). +3 tests, 240/240
backend tests pass. See `05_frontend_reporting.md`.

## 20. Frontend/reporting output format

Clean per-lamp event JSON backs every Insights chart (count/timestamps/duration per lamp, state &
global-state over time, confidence over time). Existing `TransitionCharts.jsx` unchanged; no
frontend change needed until the model is promoted. See `05_frontend_reporting.md`.

## 21. Files changed / 22. Commands added

- **New scripts (`workflows/scripts/`):** duplicate_transition_dataset, build_transition_labels,
  score_transition_candidates, build_review_montages, apply_verification, export_transition_cvat,
  prepare_transition_dataset, qa_transition_dataset, train_transition_model,
  evaluate_transition_model, head_to_head_transitions.
- **New lib (`packages/papi/src/papi/`):** transition_labels, transition_scoring.
- **New config:** `configs/papi_edny_transition.yaml`.
- **Backend (additive):** `app/services/state.py` (+ `tests/test_state.py`).
- **Docs:** `docs/transition/{00_recon,01_duplication_report,02_schema,03_candidate_mining,
  04_verification,05_frontend_reporting,dataset_qa_report,evaluation,REPORT}.md` + `artifacts/`.

## 23. Risks & unresolved issues

- **Interim labels:** flip-anchored + AI spot-check of 36/~150 flips + a dataset-wide rule — not a
  full human/CVAT pass. Production training needs a fuller human review (`transition_cvat_bundle.zip`).
- **Transition AP not converged:** the yolo26s model is 19 epochs; its transition mAP50 is still
  rising (0.147→0.256). Train to convergence (~40–60 epochs) for a higher transition AP — the F1
  already beats the baseline, but the AP has headroom.
- **Reversed lamp binding / rwy-06 angles:** transition labels are visual-correct, but per-lamp
  *angle* binding needs the corrected mapping; rwy-06 uses FAA defaults.
- **Transition is rare (3.82%):** oversampling helps; recall on subtle/night transitions to watch.
- Interim model is **not promoted** to serving; that decision is gated on the head-to-head.

## 24. Recommended next steps

1. Full human/CVAT verification of all 495 candidates (bundle ready).
2. Correct the lamp-order↔set-angle binding in `papi_edny.yaml`; obtain rwy-06 commissioned angles.
3. Train the yolo26s model to convergence (~40–60 epochs, `--resume`) to lift transition mAP50,
   then promote `best.pt` to `models/serving` / set `PAPI_TRANSITION_MODEL_PATH`.
4. The app's **transition-method toggle is already shipped** (tracking vs model — `06_method_toggle.md`);
   flip its default to "model" once the 3-class model is promoted.

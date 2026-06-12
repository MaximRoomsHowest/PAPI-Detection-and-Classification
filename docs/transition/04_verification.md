# Phase 5 — Manual Verification

## What was done

Local CVAT (`C:\Users\rodri\source\cvat`, the real `cvat-ai/cvat`) could not be brought up —
**Docker Desktop's daemon is down** and standing up its ~10-container stack headlessly is
impractical. Verification was instead performed through a **purpose-built browser review app**
(also better suited: it shows the temporal before→flip→after sequence CVAT can't), and a
**CVAT-importable 3-class bundle** was produced so the CVAT path works the moment Docker is up.

**Review unit = the flip event.** One red↔white flip seeds ~4 window candidates that share a
verdict, so reviewing per flip is both more accurate and far more tractable than 495 per-frame
clicks. `build_review_montages.py` rendered **36 flips** (stratified across runway × type × flag)
as montage strips — the tracked lamp's crop across `[flip−3 … flip+3]`, annotated with frame
index, original label state, and seeded-frame borders (`docs/transition/artifacts/review_example_page.png`).
The app (`review.html`, served over a local static server, driven via Chrome MCP) displays the
montages + decision table.

## Findings (visual spot-check of 36 flips, all strata)

| Stratum | Verdict | Why |
|---|---|---|
| Wide-camera, clean (DJI_010/011, rwy-24) | **genuine** | red_ratio↓ + white_ratio↑ + saturation↓ over ~4 frames — textbook blend |
| Wide-camera, rwy-06 night (DJI_019/020) | **genuine** | clear red↔white change; only the precise set-angle is uncertain (FAA default), not the visual |
| Wide-camera, `elev_discontinuity` | **genuine, angle unreliable** | visual change is real; the telemetry angle at the flip is junk (e.g. 4.55°→1.14° in one frame) |
| Zoom-camera, `fallback_identity` (DJI_031/040) | **ambiguous** | left-to-right lamp id on mirrored zoom is unstable; the "flip" may be a tracking artifact |

The spot-check **validated the Phase 4 ranking itself**: the `fallback_identity` flag pre-identified
exactly the unreliable cases. Confirmation rate on flip-anchored seeding ≈ **high** (only the
zoom/fallback stratum failed).

> **Note (2026-06-09):** the `elev_discontinuity` verdict above ("genuine, angle unreliable") was
> overturned by the colour audit — those windows are telemetry gaps whose crops are stable colours
> (e.g. red_ratio 0.86 three minutes from the flip), so they are now reverted, not accepted. See
> the decision rule below.

## Decision rule applied dataset-wide (`apply_verification.py`)

Updated **2026-06-09**: each verdict now combines the per-flip review flag with a per-crop
**colour verdict** (`papi.transition_scoring.classify_lamp_colour`), so a flip-anchored box is
kept as class 2 only when the crop is *visibly* an amber blend — not a stable colour that merely
sits inside a flip's frame window:

- `fallback_identity` → **ambiguous_review** → revert that box to its human red/white label
  (excluded: left-to-right lamp identity on zoom/mirrored geometry is unreliable; the "flip" may
  be a tracking artifact).
- `elev_discontinuity` → **reverted_telemetry_gap** (excluded). The flip's from/to frames sit at
  very different elevations, so the sampled window does **not** bracket a captured colour change —
  the real flip fell in an unsampled telemetry gap and both sides are stable observations. (The
  earlier rule accepted these with an `angle_unreliable` note; the 2026-06-09 audit showed the
  crops are solid colours, so that assumption was wrong.) If such a crop nevertheless *reads*
  intermediate, the signals contradict each other: it keeps its tracked label but lands in a
  distinct **reverted_telemetry_gap_ambiguous_colour** bucket queued for human review.
- crop colour is a clearly stable `red`/`white` → **reverted_stable_colour** (excluded:
  window-edge colour bleed, not a transition).
- otherwise (amber/blended crop) → **accepted_transition** (flip-anchored + colour-confirmed).
  A crop with too few lit pixels to judge (`unknown`) is accepted on the flip evidence alone and
  noted as such — never described as colour-confirmed.

## Outcome (after the 2026-06-09 colour-gate cleanup)

- 495 candidates → **250 accepted_transition**; 245 excluded/reverted: **8 ambiguous_review**,
  **205 reverted_stable_colour**, **32 reverted_telemetry_gap** (counts per
  `dataset_qa_report.md`).
- **250 final transition boxes** — 1.96% of all boxes; train 216 / val 28 / test 6.
- History: the original rule (which accepted `elev_discontinuity`) had produced **487** transition
  boxes; the colour gate reverted 237 of them (~49%) as stable-colour mislabels.
- `verification_log.csv` (brief schema: `candidate_id, decision, old_label, new_label,
  reviewer_note, source_id, frame_number, track_id`) — tracked in `artifacts/`.
- CVAT bundle: `export_transition_cvat.py` → 3-class `data.yaml` + 319 train / 79 val transition
  frames (`artifacts/cvat_data.yaml`; full zip in the git-ignored twin).

## Honesty notes

- This is an **AI-performed** structured visual review (every reviewed flip was actually
  inspected), not a domain-expert sign-off. `verification_log.csv` records each decision + its
  evidence so a human can audit/override. The `[visually reviewed]` note marks the 36 explicitly
  inspected flips; the rest carry the rule derived from them.
- 36 of ~150 flips (~24%) were inspected directly; the rule was applied to the rest. A fuller
  human pass (or CVAT once Docker is up, using `transition_cvat_bundle.zip`) can extend this.

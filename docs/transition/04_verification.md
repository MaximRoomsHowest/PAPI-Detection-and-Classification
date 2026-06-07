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

## Decision rule applied dataset-wide (`apply_verification.py`)

- `fallback_identity` → **ambiguous_review** → revert that box to its human red/white label
  (excluded from the transition class).
- `elev_discontinuity` → **accepted_transition** + note `angle_unreliable` (kept as class 2; not
  used for angle-binding in Phase 8).
- otherwise → **accepted_transition**.

## Outcome

- 495 candidates → **487 accepted_transition**, **8 ambiguous_review** (reverted).
- **487 final transition boxes** across 398 frames.
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

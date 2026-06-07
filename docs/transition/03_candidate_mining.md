# Phase 3+4 — Candidate Mining, Colour & Temporal Scoring

## Headline finding: the config lamp-order↔set-angle binding is reversed

The first implementation seeded `transition` from the **geometric blend zone**
(`|approach_elevation − set_angle| ≤ 0.10°`). Diagnostics killed it:

- For `DJI_202604281910_010_UgCS` lamp_1, the geometry seeded frames **83–90, 264–273, 408–423,
  720–741**, but the lamp's *actual* red↔white flips (`transitions.csv`, from human-corrected
  labels) are at **144, 188, 311, 331, 528, 577** — **zero overlap**.
- Cause: all four lamps are angularly co-located from drone stand-off (elevations differ ~0.002°),
  so PAPI physics is *one approach elevation vs four set-angle thresholds*. lamp_1 actually flips
  at elevation **≈3.57°**, matching **light_4's 3.60°**, not the **2.32° (light_1)** the config
  binds to `physical_lamp_id=1`. The `physical_lamp_id`→set-angle binding is **reversed** — the
  unresolved "Punktnummer" binding flagged in BigBrain.

**Data-derived (empirical) per-lamp set-angles**, median approach-elevation at each lamp's flips:

| tracks lamp | empirical set-angle | nearest commissioned (reversed) |
|---|---|---|
| lamp_1 | **3.43°** | light_4 = 3.60° |
| lamp_2 | **2.99°** | light_3 = 3.12° |
| lamp_3 | **2.49°** | light_2 = 2.55° |
| lamp_4 | **2.18°** | light_1 = 2.32° |

Descending vs the config's ascending order ⇒ reversed binding, now quantified. (Differences from
the commissioned values are within ~0.05–0.17°, consistent with the datum/averaging caveats.)

## Method actually used: flip-anchored seeding

Genuine transitions are anchored to the authoritative `transitions.csv` flips and confirmed by
colour, not invented from geometry:

1. **Anchor** — for each red↔white flip (frames `from`→`to`), promote that tracked lamp's box to
   class 2 over a **±2-frame window** (`build_transition_labels.py --half-window 2`). Only the
   transitioning lamp in those frames changes; all other lamps/frames keep their human red/white
   labels.
2. **Colour validation** (`transition_labels.colour_features`) — HSV/Lab summary of the inner-60%
   crop. The flip is visibly real: at flip 144→145 `red_ratio` falls 0.39→0.25→0.11→0.00,
   `white_ratio` rises 0.06→0.15, saturation drops 137→117 over ~4 frames; a "graze" frame far
   from any flip stays solid red (`red≈0.55, white≈0.05, sat≈178`). Colour ranks/confirms, never
   labels.
3. **Geometry** — kept only to derive the empirical set-angles above and to flag flips with
   **discontinuous telemetry** (>0.5° elevation jump between consecutive frames, e.g. lamp_1's
   flip at 188: 4.55°→1.14°) for mandatory human review.

Why not detector-based ByteTrack mining (the brief's literal Phase 3)? The dataset already ships
human-verified per-lamp tracks (`tracks.csv`) and flips (`transitions.csv`) — a stronger anchor
than re-running a noisy detector. Live ByteTrack is used where it belongs: Phase 9 inference.

## Colour analysis method

Inner-60% bbox crop → OpenCV HSV + Lab. Features per candidate: `red_ratio` (hue≈0/180, sat>60,
val>60), `orange_amber_ratio` (hue 11–25), `yellow_ratio` (hue 26–35), `white_ratio` (sat<45,
val>170), `sat_mean`, `val_mean`, `hue_median`, `lab_a_mean`, `lab_b_mean`. Lesson: small
overexposed lamps read amber even when stable, so **absolute** colour is a weak per-frame signal;
the **temporal change** (red↓/white↑/sat↓ across the window) is the reliable cue. Colour therefore
refines the rank; it never sets a label.

## Temporal method

The flip itself is the temporal evidence: `previous_state` (stable colour before) and `next_state`
(stable colour after) come straight from the flip and always differ (a genuine crossing).
`frame_offset` (signed distance from the flip boundary) measures how central a window frame is.

## Scoring & ranking (`papi.transition_scoring`)

`transition_score = 0.6·offset_proximity + 0.4·colour_intermediacy`, tiered into
`high / medium / low / ambiguous`. `review_flag` forces human attention regardless of score for
`elev_discontinuity`, `fallback_identity` (left-to-right lamp id), and `rwy06_faa_default`
(commissioned angles pending).

## Candidate statistics

- **495 candidates** (305 red→white, 190 white→red), balanced across lamps (136/134/120/105).
- Tiers: **47 high, 354 medium, 62 low, 32 ambiguous**.
- Review-flagged: **164** — 124 rwy-06 (FAA-default angles), 32 elev-discontinuity, 8 fallback-id.
- ~3.9% of the ~12,761 boxes — a real, trainable minority class (not the 975 noise-filled grazes
  the geometric attempt produced).

## Outputs (all in the git-ignored twin)

`transition_candidates.csv`, `transition_candidates_ranked.csv`, `transition_labels_manifest.json`
(incl. empirical set-angles), `transition_ranking_manifest.json`; class-2 labels written into
`…/labels/*.txt`.

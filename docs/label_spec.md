# Label specification — PAPI Detection and Classification

This document describes the labelling conventions for the dataset auto-labelled in sprint 1 and
verified in CVAT in sprint 2. Pin this doc when training; update it (with a CHANGELOG entry at
the bottom) whenever a convention changes.

## Detection class taxonomy

For the final model scope, use one bbox per visible lamp and encode the lamp state as the
detection class:

| `class_id` | name | description |
|---:|---|---|
| 0 | `papi_light_red` | One visible PAPI lamp whose geometric state is red. |
| 1 | `papi_light_white` | One visible PAPI lamp whose geometric state is white. |

Transitions are no longer a detector class. Infer red/white changes later by
tracking the same lamp across the frame sequence.

The tracking annotation source of truth is stored per video in `tracks.csv`.
Transition events are stored separately in `transitions.csv` and currently
report consecutive-frame `white_to_red` and `red_to_white` switches.

The older `papi_installation` class was useful for a first detector smoke test, but it is not
sufficient for the project scope because it collapses the four lamps into one object. Keep it only
for installation-level debugging exports.

## Bounding-box convention

- One box per visible lamp glow, not one box around the whole PAPI installation.
- The auto-label is built from each projected lamp pixel center, with a square bbox sized from
  neighbouring projected lamp spacing and a minimum half-size of 10 px.
- If only 1–3 lamps are projected in-frame, only those visible lamps are written.
- If 0 lamps are in-frame or the frame is ZoomCamera without calibrated focal length, the label
  file is kept empty so CVAT still loads the frame for manual review.

## Per-lamp ordering

Lights are numbered **1 (innermost) to 4 (outermost)** following the surveyed XLSX ordering at
`..\PAPI-artifacts\2026-05-26-cleanup\PROJECT1-PAPI\PAPI_Coords_Fred_DE.xlsx`.
This matches the FAA standard where the innermost
light has the **lowest** set-angle (closest to the glideslope; turns red first when the pilot
sinks below path):

| Light | FAA default set-angle (3.0° glideslope) | Pilot meaning when below set-angle |
|---:|---:|---|
| 1 | 2.50° | First to turn red; "slightly low" |
| 2 | 2.83° | Second; "low" |
| 3 | 3.17° | Third; "high" |
| 4 | 3.50° | Last to turn red; "well above path" |

The set-angles in `configs/papi_edny.yaml` are flagged TODO — Intersoft has not yet confirmed
the EDNY commissioned set-angles for either runway. Until then, the FAA defaults are used.
When real values arrive, fill in `runways.<06|24>.papi.light_<i>.set_angle_deg` in the YAML
and the lamp-state geometry recomputes correctly without code changes.

**Dual runway**: the dataset contains flights targeting both runway 06 (5 night flights) and
runway 24 (16 day flights). The per-frame `target_runway` column in `data/interim/lamp_state.csv`
records which PAPI was used.

## Per-lamp state values

| value | meaning | how auto-derived |
|---|---|---|
| `white` | lamp viewed from above its set-angle cone (pilot is on or above path for this light) | `elevation_camera_seen_from_light > set_angle + transition_half_width` |
| `red` | lamp viewed from below its set-angle cone (pilot is below path for this light) | `elevation_camera_seen_from_light < set_angle - transition_half_width` |
| `transition` | within the narrow angular blend zone where the lamp visually mixes | within `transition_half_width` of `set_angle` |

`transition_half_width_deg` defaults to 0.10° (a slightly conservative widening of the real
PAPI lens transition, which is typically ~3 arcminutes ≈ 0.05°).

## Global glidepath state (5 + 1 categories)

| code | per-lamp pattern | pilot interpretation |
|---|---|---|
| `4W` | white-white-white-white | well above glideslope |
| `3W1R` | white-white-white-red | slightly above |
| `2W2R` | white-white-red-red | on glideslope |
| `1W3R` | white-red-red-red | slightly below |
| `4R` | red-red-red-red | well below |
| `TRANSITION` | any lamp is transition | between two of the above; visually mixed |

## Failure modes & disagreement handling

- **Daylight lens flare**: the sun or a bright cloud can saturate a red lamp to look white. If
  the geometric prediction is `red` but the verifier sees white, log the disagreement and
  **trust the verifier**. These are exactly the frames training needs to learn the regime.
- **Night halo / diffraction**: bbox the lamp glow itself, not the wider diffraction halo from
  the camera optics. The auto-bbox is tight enough; verifiers should not enlarge it.
- **Partial occlusion** (e.g. a row of taxiway lights overlapping with PAPI in the frame):
  keep the bbox tight to the PAPI cluster; do not annotate adjacent ground lights as PAPI.
- **Auto-label projects to "wrong" pixels**: usually means GPS/gimbal jitter or RTK-Single
  position noise. Verifiers correct the bbox; the next sprint computes per-regime agreement so
  these aren't averaged away.
- **`global_state == TRANSITION`** but the verifier sees a discrete state — record the verifier
  state in CVAT; the agreement script will flag this as a per-lamp transition-width tuning
  signal.

## Sprint-2 additions (placeholder)

- ZoomCamera auto-labels once Intersoft provides calibrated focal length.
- A "false positive" / "no PAPI visible" class for negative samples once we have other-runway
  or non-airport frames.

## Changelog

- 2026-05-19 — initial spec; one class, geometry-derived bbox, FAA-default set-angles.
  Also: discovered the dataset targets both runways (06 night, 24 day), not just runway 06
  as the dataset note had claimed; the pipeline picks the nearer PAPI per frame.
- 2026-05-19 — corrected CVAT verification export to per-lamp state classes:
  `papi_light_red`, `papi_light_white`, `papi_light_transition`.
- 2026-05-24 — canonical detector taxonomy reduced to two classes:
  `papi_light_red` and `papi_light_white`. Transition handling moved to the
  temporal tracking layer instead of YOLO labels.

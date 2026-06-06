# Data Card — EDNY PAPI Sequence Dataset

Honest dataset documentation (audit IMP-DOC-8). Dataset-handling rules live in
[`data/README.md`](../data/README.md) and label semantics in
[`docs/label_spec.md`](label_spec.md); this card adds composition, provenance, splits
and known-bias framing.

## Overview

- **Domain**: drone imagery of Precision Approach Path Indicator (PAPI) lights at
  **Bodensee-Airport Friedrichshafen (EDNY)**, Germany.
- **Capture**: DJI Matrice 4E drone, two sensors — **WideCamera** and **ZoomCamera**.
- **Scale**: ~4,000 frames across multiple flights (the canonical dataset is archived
  externally and referenced via the `.gitignore` whitelist, not committed to git).
- **Runways**: a single physical runway with two designations — **rwy 06** (night
  flights, PAPI at the SW end) and **rwy 24** (day flights, PAPI at the NE end). Early
  documentation assumed rwy-06 only; that was corrected (see `docs/pipeline.md`).

## Regimes (and why they're split out)

| Regime | Notes |
| --- | --- |
| Day — WideCamera | The hard case: sun glare, washed-out red/white separation. |
| Day — ZoomCamera | Degraded until `calibrated_focal_px` is supplied (`configs/papi_edny.yaml`). |
| Night — WideCamera | Easier separation; must not be allowed to mask day performance. |

Evaluation is **viewpoint-aware**: metrics are reported per regime, not only aggregate,
so daytime weakness is visible (per the client's kickoff guidance).

## Labels

- Two detection classes: `papi_light_red`, `papi_light_white` (see `label_spec.md`).
- **Auto-labelled by geometry**: surveyed lamp coordinates are projected into image
  space using the calibrated camera model (`workflows/scripts/pipeline.py` →
  `autolabel`), then verified/corrected in CVAT — not hand-drawn from scratch.
- The per-lamp *transition* state is **not** a labelled class: at inference time it is
  inferred *temporally* — each lamp is tracked across frames and a red/white flip is
  detected (`app/services/state.py` → `detect_lamp_transitions`), with the viewing angle
  only annotating the event. (The offline auto-labelling path separately uses the
  elevation-angle-vs-set-angle band in `packages/papi/src/papi/lamp_state.py` to *seed*
  labels — that is not the runtime path.)

## Splits

Flight-level, regime-aware, defined in [`configs/split.yaml`](../configs/split.yaml):
train / val from mixed flights, with specific regimes (e.g. a 500 m night-wide flight)
**held out as test** so evaluation isn't leaked by adjacent frames of the same flight.

## Provenance & known issues

- Coordinates come from `PROJECT1-PAPI/PAPI_Coords_Fred_DE.xlsx` (Intersoft).
- **Geometry caveat**: rwy-24 uses the validated `461.37 m` reference. Rwy-06 also
  uses `461.37 m` from the data-analysis branch
  (`PAPI_06_df["altitude"] = 461.37`). The branch's `464.988 m` value is a minimum
  client drone EXIF/MRK altitude floor proxy and is not used as lamp height.
  Lamp numbering and commissioned set-angles still need binding.
- The training-split git SHA should be recorded per run in `models/MODELS.md`.

## Biases & limitations

- **Single airport** — generalisation to other airports is untested (the library supports
  per-airport YAML but no second airport is in the dataset).
- **Class/regime imbalance** — day vs night and red vs white are not guaranteed balanced;
  see the data-analysis notebook (`workflows/notebooks/05_data_analysis.ipynb`).
- **No personal data** — imagery is of runway infrastructure only.

## Sources

- [`data/README.md`](../data/README.md), [`docs/label_spec.md`](label_spec.md),
  [`docs/pipeline.md`](pipeline.md), [`configs/split.yaml`](../configs/split.yaml),
  [`models/MODELS.md`](../models/MODELS.md).

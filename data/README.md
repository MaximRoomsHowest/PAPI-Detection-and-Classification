# `data/` — datasets and data-pipeline I/O

This folder holds **data only** — image/label datasets and the pipeline's
intermediate files. **Models never live here**: every trained weight, run, and the
serving slot live under [`models/`](../models/) (see [`models/MODELS.md`](../models/MODELS.md)).
Training output is written to `models/runs/experiments/`, *not* `data/`.

## What is committed vs. ignored

Only small, shareable fixtures are committed; the large/proprietary working data is
git-ignored and stays local (recreate it with the `workflows/scripts/` builders, or
junction it from the archive below).

| Path | Tracked | What it is |
|------|---------|------------|
| `eval/<id>/` | **committed** | Built-in evaluation seeds shipped with the app — `images/` + `labels/` + `README.md`. Two sets: `builtin-detector-redwhite` (2-class) and `builtin-transition-3class` (3-class). The backend copies these into its datasets store on startup (`PAPI_EVAL_SEED_DIR`). |
| `datasets/<id>/` | git-ignored | Full train/eval datasets (large). `papi-2class-detection-flightsplit` (2-class detector, flight-level split) and `transition-classification-data/` (the 3-class transition twin; `transition_combined/` is the trainable dataset). Registered in-place on the Datasets page via `PAPI_PROJECT_DATASETS_DIR`. |
| `raw/`, `interim/`, `labels/`, `annotations/`, `cvat/`, `work/` | git-ignored | Pipeline I/O: raw client frames, extracted metadata, label tables, CVAT corrections, scratch. `.gitkeep` placeholders keep the empty scaffolding; the contents are ignored. |

The committed-vs-ignored rules live in [`.gitignore`](../.gitignore) (`data/` block).

## Where the rest of the pipeline lives

- **Notebooks** → [`workflows/notebooks/`](../workflows/notebooks/) (`01_…` → `09_…`).
- **Scripts** → [`workflows/scripts/`](../workflows/scripts/) (dataset builders, eval, training, CVAT export).
- **Configs** → [`configs/`](../configs/) (`papi_edny.yaml`, `split.yaml`, `projection.yaml`, `weather_yaml/`).
- The runtime upload / assisted-label dataset store is **app-local**, not here:
  `apps/backend/storage/datasets/` (a Docker named volume `/datasets` in compose).
  So there are three dataset tiers — committed seeds (`data/eval`), local full sets
  (`data/datasets`), and the runtime store — kept separate by lifecycle.

## Archive

The large pre-cleanup data folders were archived outside the repo to keep Git lean:
`..\PAPI-artifacts\2026-05-26-cleanup\data\`. Recreate or junction folders locally
from there when a workflow needs them; do not commit generated data under `data/`.

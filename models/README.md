# Local Model Weights — filesystem layout

This file covers **where the files live**. For model lineage, metrics, and
deployment status see the registry: [`models/MODELS.md`](MODELS.md).

## Layout

| Path | Type | Purpose |
|---|---|---|
| `models/base/*.pt` | Base weights | Upstream Ultralytics seeds (yolo26n / yolo26s / yolo26m) for fine-tuning. |
| `models/runs/detect/<arch>-<dataset>-<res>/` | Trained runs | Each run's `args.yaml`, `results.csv`, plots, and `weights/best.pt` + `last.pt`. Named so the folder tells you the model — see MODELS.md §0. |
| `models/serving/best.pt` | Serving slot | The model the FastAPI backend loads by default. A **copy** of the active run's `best.pt`; the slot filename is stable (see below). |
| `models/serving/model_card.json` | Provenance | Identifies which run is in the slot + its val metrics; served by `/api/model`. |
| `models/serving/best_int8.onnx` | INT8 export | Quantised export of the **previous** yolo26n model; experimental / CPU-broken (MODELS.md §3.2.1). |

> **Git tracking:** `.gitignore` ignores `*.pt`/`*.onnx` globally but
> **un-ignores** `models/base/*`, `models/serving/*`, and `models/runs/**`,
> so the weights under those paths **are** committed. Weights under
> `data/runs/` (the data_analysis workspace) stay ignored.

## Serving model

The backend loads `models/serving/best.pt`. As of **2026-05-31** the slot
holds **`yolo26s-fulldata-1280`** (the higher-resolution full-dataset run
from the `data_analysis` branch):

```text
models/runs/detect/yolo26s-fulldata-1280/weights/best.pt   ->   models/serving/best.pt
```

To rotate the serving model, copy a different run's `best.pt` into the slot
and regenerate the card — full procedure in [`models/MODELS.md`](MODELS.md) §5.
The slot filename stays `best.pt` (the Dockerfile, compose, `.env`, and docs
all reference it).

To roll back to the previous yolo26n model:

```powershell
Copy-Item models\runs\yolo26n-sequence-1280\weights\best.pt models\serving\best.pt -Force
..\..\.venv\Scripts\python.exe workflows\scripts\populate_model_metrics.py `
  models\runs\yolo26n-sequence-1280 --write-model-card models\serving\model_card.json
```

## Deprecated archived runs

Historical runs predating the current label spec live outside the repo at
`..\PAPI-artifacts\2026-05-26-cleanup\runs\papi\` and must not be used for
the integrated app — see MODELS.md §4.

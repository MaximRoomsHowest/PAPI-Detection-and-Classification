# Local Model Weights — filesystem layout

This file covers **where the files live**. For model lineage, metrics, and
deployment status see the registry: [`models/MODELS.md`](MODELS.md).

## Layout

| Path | Type | Purpose |
|---|---|---|
| `models/base/*.pt` | Base weights | Upstream Ultralytics seeds (yolo26n / yolo26s / yolo26m) for fine-tuning. |
| `models/runs/detect/<arch>-<dataset>-<res>/` | Trained runs | Promoted handover runs keep `weights/best.pt` plus `args.yaml`, `results.csv`, and optional `model_card.json` / `detector_train_meta.json`. Training-only plots, preview batches, and `last.pt` resume checkpoints are regenerated artifacts. |
| `models/serving/best.pt` | Serving slot | The model the FastAPI backend loads by default. A **copy** of the active run's `best.pt`; the slot filename is stable (see below). |
| `models/serving/model_card.json` | Provenance | Identifies which run is in the slot + its val metrics; served by `/api/model`. |
| `models/serving/models.json` | Runtime registry | Backend-owned selector options served by `/api/models`; includes `small`, `nano`, and the optional transition classifier with availability checks. |
| INT8 export | Retired path | **Not shipped.** The old quantised export failed on CPU ONNX Runtime (`ConvInteger` unimplemented). Deploy `best.pt`, the fp32 ONNX export, or the OpenVINO export instead. |

> **Git tracking:** `.gitignore` ignores `*.pt`/`*.onnx` globally but
> **un-ignores** `models/base/*`, `models/serving/*`, and promoted
> `models/runs/**` handover artifacts. Weights under `data/runs/` and
> in-progress runs under `models/runs/experiments/` stay ignored.

## Selectable serving models

The backend reads `models/serving/models.json` as the source of truth for
selectable inference models. The default `small` entry points at
`models/serving/best.pt`. As of **2026-05-31** that slot holds
**`yolo26s-fulldata-1280`** (the higher-resolution full-dataset run from the
`data_analysis` branch):

```text
models/runs/detect/yolo26s-fulldata-1280/weights/best.pt   ->   models/serving/best.pt
```

The registry also exposes:

- `nano` — previous `yolo26n-sequence-1280` detector for rollback/comparison.
- `transition` — `transition3class-yolo26s-1280`, a 3-class transition
  classifier committed at
  `models/runs/detect/transition3class-yolo26s-1280/weights/best.pt` and
  available by default. Experimental (low transition-class recall) — see
  MODELS.md §5c. If the weight is absent, `/api/models` marks it unavailable
  and the Live Demo disables it.

To rotate the serving model, copy a different run's `best.pt` into the slot
and regenerate the card — full procedure in [`models/MODELS.md`](MODELS.md) §5.
The slot filename stays `best.pt` (the Dockerfile, compose, `.env`, and docs
all reference it).

To roll back to the previous yolo26n model, from the repo root:

```powershell
Copy-Item models\runs\detect\yolo26n-sequence-1280\weights\best.pt models\serving\best.pt -Force
.venv\Scripts\python.exe workflows\scripts\populate_model_metrics.py `
  models\runs\detect\yolo26n-sequence-1280 --write-model-card models\serving\model_card.json
```

## Deprecated archived runs

Historical runs predating the current label spec live outside the repo at
`..\PAPI-artifacts\2026-05-26-cleanup\runs\papi\` and must not be used for
the integrated app — see MODELS.md §4.

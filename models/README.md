# Local Model Weights

Model binaries are intentionally ignored by Git.

## Current Local Files

| Path | Type | Purpose |
|---|---|---|
| `models/base/yolo26n.pt` | Base weight | Small YOLOv26 base model for notebook 03 and quick local retraining. |
| `models/base/yolov26m.pt` | Base weight | Preferred larger YOLOv26m base model for active-learning experiments. |
| `models/runs/yolo26n_sequence_red_white_safe/` | Current trained run | Local canonical run metadata and checkpoint for the active sequence model. |
| `models/serving/best.pt` | Deployment alias | Runtime model loaded by the FastAPI backend by default. Keep this copied from the active run checkpoint. |

`models/base/yolo11n.pt` was removed from the local workspace because YOLO11 was
an early deprecated experiment and is not referenced by the current notebooks or
backend.

## Serving Model

For current app testing, the canonical local run checkpoint is:

```text
models/runs/yolo26n_sequence_red_white_safe/weights/best.pt
```

The backend runtime alias is:

```text
models/serving/best.pt
```

To restore the current run from the archive:

```powershell
Copy-Item ..\PAPI-artifacts\2026-05-26-cleanup\runs\papi\yolo26n_sequence_red_white_safe\args.yaml models\runs\yolo26n_sequence_red_white_safe\args.yaml -Force
Copy-Item ..\PAPI-artifacts\2026-05-26-cleanup\runs\papi\yolo26n_sequence_red_white_safe\results.csv models\runs\yolo26n_sequence_red_white_safe\results.csv -Force
Copy-Item ..\PAPI-artifacts\2026-05-26-cleanup\runs\papi\yolo26n_sequence_red_white_safe\weights\best.pt models\runs\yolo26n_sequence_red_white_safe\weights\best.pt -Force
Copy-Item models\runs\yolo26n_sequence_red_white_safe\weights\best.pt models\serving\best.pt -Force
```

To prepare the backend from the small base weight instead:

```powershell
Copy-Item models\base\yolo26n.pt models\serving\best.pt -Force
```

For project-quality YOLOv26m demos, copy the intended trained YOLOv26m checkpoint
into `models/serving/best.pt` before starting the backend.

## Deprecated Archived Runs

Historical runs remain outside the repo at:

```text
..\PAPI-artifacts\2026-05-26-cleanup\runs\papi\
```

Treat everything except `yolo26n_sequence_red_white_safe` as deprecated training
lineage. Do not use those checkpoints for the integrated app unless explicitly
comparing historical experiments.

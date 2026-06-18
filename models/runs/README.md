# Model Runs

Trained run artifacts, one folder per run, named `<arch>-<dataset>-<res>`
(see [`models/MODELS.md`](../MODELS.md) §0 for the convention).

```text
models/runs/detect/yolo26s-fulldata-1280/   <- current serving source
models/runs/detect/yolo26s-fulldata-640/
models/runs/detect/yolo26s-augmented/
models/runs/detect/yolo26s-baseline/
models/runs/detect/yolo26n-baseline/
models/runs/detect/yolo26s-extra-aug/        <- extra-augmentation experiment
models/runs/detect/yolo26s-weather-aug/      <- weather-augmentation experiment (train-9; rain/fog/haze only)
models/runs/detect/yolov8s-transfer/
models/runs/detect/yolo26n-sequence-1280/           <- previous serving (rollback)
models/runs/detect/yolo26n-weather-flightsplit-1280/ <- weather-robust nano (2026-06-18; leak-free + OpenCV weather)
```

Each run tracks `args.yaml`, `results.csv`, training/validation plots, and
`weights/best.pt` + `last.pt` (the weights are committed — `models/runs/**`
is un-ignored in `.gitignore`).

**Committed runs vs. the training workspace.** `models/runs/detect/` holds the
**committed, registered** runs (every weight tracked). In-progress and experimental
runs land in **`models/runs/experiments/`**, which is **git-ignored** — so every model
lives under `models/` (one place), but only promoted runs are committed. The training
scripts write there (`--project models/runs/experiments`); promote a finished run by
copying it to `models/runs/detect/<run>/` and registering it in
`models/serving/models.json` (MODELS.md §5). Nothing trained should land in `data/` —
`data/` is for datasets only.

The backend does **not** load from here. It loads the serving slot
`models/serving/best.pt`, which is a copy of the active run's `best.pt`
(promotion procedure: MODELS.md §5).

Historical runs predating the current label spec live only in the external
archive `..\PAPI-artifacts\2026-05-26-cleanup\runs\papi\`.

## Weather-augmentation experiments (imported from `data_analysis`)

Two `yolo26s` detectors trained on the 2-class `PAPI_Split` set (100 epochs,
640 px) extend the augmentation pipeline beyond the baseline. Both were the raw
ultralytics runs `train-8` / `train-9` on the `data_analysis` branch; they are
renamed here to follow the `<arch>-<dataset>-<res>` convention.

| Folder                  | Source run | Augmentation focus                                              |
|-------------------------|------------|-----------------------------------------------------------------|
| `yolo26s-extra-aug`     | `train-8`  | Extra Albumentations: mixup, copy-paste (flip), erasing, HSV, rotation |
| `yolo26s-weather-aug`   | `train-9`  | Above **plus** synthetic weather (rain / fog / haze)            |

### Weather-robustness validation (`val-12` … `val-15`)

`yolo26s-weather-aug` (`train-9`) re-validated on synthetic weather variants of
the `PAPI_Split` valid split. Full notebook + degradation plots:
[`workflows/notebooks/09_weather_evaluation.ipynb`](../../workflows/notebooks/09_weather_evaluation.ipynb)
(condition transforms in [`workflows/scripts/weather_aug.py`](../../workflows/scripts/weather_aug.py) and
[`configs/weather_yaml/`](../../configs/weather_yaml/)).

| Run      | Condition | mAP50 | mAP50-95 |
|----------|-----------|-------|----------|
| `val-12` | clear     | 0.949 | 0.637    |
| `val-13` | rain      | 0.947 | 0.628    |
| `val-14` | fog       | 0.663 | 0.271    |
| `val-15` | haze      | 0.682 | 0.293    |

Takeaway: the detector is robust to rain (≈clear) but degrades sharply under
fog — the headline result behind the weather-degradation graphs.

`val-5` / `val-6` / `val-7` are additional validation runs imported from the
same branch (provenance not recorded in their folders — no `args.yaml`).

### Weather-robust nano (2026-06-18) — supersedes the experiments above

`yolo26n-weather-flightsplit-1280` is a clean, leak-free retrain that actually *trains*
on synthetic weather (rain / fog / haze / **snow** / sun-flare / shadow), not just
rain/fog/haze, and is evaluated on the held-out **test** split. Full record + the
medium/heavy robustness tables: [`models/MODELS.md` §3.2b](../MODELS.md). It is the only
model that survives snow (the old `yolo26s-weather-aug` train-9 collapses there too).

The weather transforms are now **pure OpenCV/NumPy**
([`workflows/scripts/weather_aug.py`](../../workflows/scripts/weather_aug.py)) — the old
AlbumentationsX/`albucore` path corrupted async CUDA training (MODELS.md §3.2b note). The
reproducible multi-model eval is
[`workflows/scripts/eval_weather_robustness.py`](../../workflows/scripts/eval_weather_robustness.py),
which supersedes the manual `09_weather_evaluation.ipynb` flow (that notebook still imports
albumentations and will not run against the current OpenCV-only environment).

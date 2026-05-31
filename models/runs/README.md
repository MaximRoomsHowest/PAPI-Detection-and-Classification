# Model Runs

Trained run artifacts, one folder per run, named `<arch>-<dataset>-<res>`
(see [`models/MODELS.md`](../MODELS.md) §0 for the convention).

```text
models/runs/detect/yolo26s-fulldata-1280/   <- current serving source
models/runs/detect/yolo26s-fulldata-640/
models/runs/detect/yolo26s-augmented/
models/runs/detect/yolo26s-baseline/
models/runs/detect/yolo26n-baseline/
models/runs/detect/yolov8s-transfer/
models/runs/yolo26n-sequence-1280/           <- previous serving (rollback)
```

Each run tracks `args.yaml`, `results.csv`, training/validation plots, and
`weights/best.pt` + `last.pt` (the weights are committed — `models/runs/**`
is un-ignored in `.gitignore`).

The backend does **not** load from here. It loads the serving slot
`models/serving/best.pt`, which is a copy of the active run's `best.pt`
(promotion procedure: MODELS.md §5).

Historical runs predating the current label spec live only in the external
archive `..\PAPI-artifacts\2026-05-26-cleanup\runs\papi\`.

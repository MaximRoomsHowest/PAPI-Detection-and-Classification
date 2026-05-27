# Model Runs

This folder is the local model-run workspace.

Only the current app-ready run belongs here:

```text
models/runs/yolo26n_sequence_red_white_safe/
```

Tracked metadata:

- `args.yaml`
- `results.csv`

Ignored binaries:

- `weights/best.pt`

The backend does not load directly from `models/runs/`. It loads the deployment
alias at `models/serving/best.pt`, which should be copied from the active run
checkpoint.

Historical runs are deprecated and live only in the external artifact archive:

```text
..\PAPI-artifacts\2026-05-26-cleanup\runs\papi\
```

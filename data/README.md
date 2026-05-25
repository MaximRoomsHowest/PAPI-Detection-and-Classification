# Data Folder Structure

This project now uses a video-oriented dataset layout for human-facing data.
Do not add new generated folders directly under `data/`; put temporary
rebuildable files under `work/` only when a workflow needs scratch space, and
put durable datasets under `datasets/`.

## Stable Sources

- `raw/` - original client image drop. Treat as read-only.
- `interim/` - extracted metadata, sample manifests, and pipeline intermediates.
- `labels/` - project-owned label tables and durable label metadata.
- `annotations/manual_corrections/` - CVAT exports corrected by a human. These
  are durable correction milestones and should not be deleted.

## Canonical Dataset

- `datasets/papi_lamp_sequences/daytime/` - corrected daytime frames grouped by
  source video folder.
- `datasets/papi_lamp_sequences/nighttime/` - trusted nighttime frames grouped
  by source video folder.
- Each regime folder has:
  - `<video_id>/images/*.JPG`
  - `<video_id>/labels/*.txt`
  - `<video_id>/metadata.csv`
  - `train.txt`, `val.txt`, `data.yaml`, and `manifest.json`
- `datasets/papi_lamp_sequences/validation_summary.json` records the latest
  full validation pass for both regimes.
- Each video folder also has:
  - `tracks.csv` - one row per labeled lamp box with a stable per-video
    `track_id`.
  - `transitions.csv` - consecutive-frame `white_to_red` and `red_to_white`
    switches per tracked lamp.
- `datasets/papi_lamp_sequences/tracking_manifest.json` summarizes tracking
  counts, transition counts, assignment methods, and quality flags.
- `datasets/papi_lamp_sequences/yolo26n_combined/` contains the no-copy
  train/val/test config for small YOLOv26 training from the canonical sequence
  folders.
- Detection classes are red/white only:
  - `0: papi_light_red`
  - `1: papi_light_white`

Transitions are no longer a detector class. Detect red/white changes later by
tracking each individual lamp over the frame sequence.

## Removed Generated Data

The old batch-oriented archive, temporary `work/` outputs, inactive `cvat/`
placeholder, and converted `night-time-dataset.coco.zip` were removed during
the 2026-05-24 cleanup. Use the canonical sequence dataset for training,
evaluation, and video reconstruction.

## Scratch Space

- `work/` - temporary generated files. Anything here can be rebuilt and should
  not be treated as source of truth.

## Current Workflow

1. Correct annotations in CVAT when needed.
2. Export corrected annotations into `annotations/manual_corrections/`.
3. Rebuild `datasets/papi_lamp_sequences/` by grouping frames by `video_id`.
4. Run `scripts/build_sequence_tracking.py` to assign stable lamp tracks and
   derive transition events.
5. Run `scripts/prepare_yolo_sequence_dataset.py` to refresh the combined
   `yolo26n_combined` training config.
6. Use each `<video_id>/images/` folder to reconstruct videos for live testing.

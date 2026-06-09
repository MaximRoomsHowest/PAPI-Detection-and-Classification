# PAPI Live-Demo — User-Test Material

Real, curated inputs for hands-on testing of the **Live Demo** page: PAPI drone frames across
distance / day-night / both runways, two real descent **sweeps**, and **matching telemetry**
(DJI `.SRT`, CSV, JSON) derived from the drone's actual GPS — so the elevation-angle readout shows
a real angle. Work through [`test-plan.md`](./test-plan.md) case by case.

> The frames and the model output are **real** (curated from the project's
> `data/datasets/transition-classification-data/`). The telemetry is built from each clip's real
> per-frame `metadata.csv` (`lat / lon / alt_ellipsoidal_m`). It is **test input**, not a
> re-survey — but it is the drone's own recorded position, not invented.

## Why full frames (downscaled, NOT cropped)
[`build_media.py`](./build_media.py) **downscales each full frame to 1280 px long-edge — the whole
field of view, never a crop.** This matters for a real reason, measured against the serving model:

| Input fed to the model | Lamps detected (ground truth: 4) |
|------------------------|----------------------------------|
| Full frame / downscaled-full (1280 px) | **4 / 4** ✅ |
| 1600×1200 PAPI-centred **crop** | **0 / 4** ❌ |

The detector is trained on full frames and resizes internally to 1280, so the lamps must keep their
full-frame scale (~6 px). A crop blows them up out of the training distribution and the model finds
**nothing**. The cost: in the main viewer a full frame is mostly sky with the PAPI a tiny cluster at
the horizon — so use the page's **"PAPI close-up"** panel (it zooms to the detected lamps) to see the
states. `build_media.py --full-res` writes the uncropped originals to `media/_fullres/` (git-ignored).

## What's here
```
media/
  single-image/                 6 frames: papi_24 day near/far/far-1000m, papi_06 night near/far
    papi24_day_300m_early.jpg     low approach (~1.6°): lamps mostly RED (too low)
    papi24_day_300m_late.jpg      high approach (~3.8°): lamps mostly WHITE (too high)
    papi24_day_700m.jpg / _1000m_far.jpg   farther standoff — smaller lamps, harder detection
    papi06_night_300m.jpg / _500m.jpg      night — bright lamps, papi_06 (provisional geometry)
  image-batch/
    sweep_papi24_300m_day/      10-frame real descent, angle climbs ~1.9° -> ~3.8°
    sweep_papi06_300m_night/    8-frame real night descent, angle ~0.85° -> ~2.6°
telemetry/
  csv/ srt/ json/               real per-frame tracks for the two sweeps + point_papi24.json (one fix)
  invalid/                      four files that each return a clean 400
build_media.py                  rebuilds the frames + telemetry from the dataset (idempotent)
generate.py                     edge/limit inputs (oversized, 81 MP, corrupt, 201-batch, …) — git-ignored
```

## Which input pairs with which telemetry — and the real expected angle
| Media | Runway | Telemetry | Real angle (computed from the geometry) |
|-------|--------|-----------|-----------------------------------------|
| `sweep_papi24_300m_day/` | papi_24 | `telemetry/{csv,srt,json}/papi24_300m_day.*` | climbs **+1.9° → +3.8°** across the 10 frames |
| `sweep_papi06_300m_night/` | papi_06 | `telemetry/{csv,srt,json}/papi06_300m_night.*` | **+0.85° → +2.6°** (papi_06 geometry provisional) |
| `single-image/papi24_day_300m_early.jpg` | papi_24 | `telemetry/json/point_papi24.json` (one fix) | ~**+1.6°** → "too low", lamps mostly red |

A browser upload strips GPS, so a plain image first returns **"angle unavailable"** and the metadata
panel appears — that's expected. Apply the matching telemetry (or type the lat/lon/alt from the
catalog) to get the real angle. All telemetry uses **absolute (WGS-84) altitude**; a relative-only
file is rejected by design.

## What the sweep should show (ground-truth-backed)
The `papi24_300m_day` sweep is a real climb through the 3° glidepath, so as you step the frames the
global verdict moves **too low (more red) → on glidepath (mixed) → too high (more white)**, and the
PAPI lamps transition **red→white** during the run (the clip's `transitions.csv` records 4 such
transitions). *Note:* the exact lamp↔set-angle binding for rwy-24 is a known open question
(lamp numbering vs. set-angle order), so judge by the **overall red/white balance**, not a specific
lamp's order.

## Cheat-sheet
**Runways** — `papi_24` (primary, trustworthy angle) · `papi_06` (provisional geometry).
**EDNY lamps** — papi_24 ≈ 47.6735 N, 9.5181 E, 461.37 m · papi_06 ≈ 47.6688 N, 9.5040 E, 461.37 m.
**Limits** (the edge files) — 100 MB/file · 80 MP/image · 600 video frames / 30 s · 200 images/folder ·
400 MB/batch · drone lat ∈[−90,90], lon ∈[−180,180], alt ∈[−500,20000] m.
**Throughput** — CPU-bound, ~0.4 fps; angle-sweep is one round-trip per image. A 10-frame sweep is
~20–30 s. Not a bug.
**Videos** — use the repo's `test_videos/*.mp4` (the root `.gitignore` ignores `*.mp4` elsewhere).

## Rebuilding / extending
```
.venv/Scripts/python.exe docs/user-testing/build_media.py            # the committed frames + telemetry
.venv/Scripts/python.exe docs/user-testing/build_media.py --full-res # full frames -> media/_fullres (git-ignored)
.venv/Scripts/python.exe docs/user-testing/generate.py               # edge/limit inputs (git-ignored)
```
Edit the `CLIPS` / `single_spec` / `sweep_spec` lists in `build_media.py` to pull different clips,
distances, or more frames from the (git-ignored) dataset.

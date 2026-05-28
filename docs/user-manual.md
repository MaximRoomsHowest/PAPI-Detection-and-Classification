# PAPI Vision — User Manual

For end users of the PAPI Vision demo application: drone operators,
review engineers, and the jury. If you want to install the system
from scratch, see [installation-manual.md](installation-manual.md)
instead.

## 1. What this application does

PAPI Vision analyses drone footage of a four-light **PAPI**
(Precision Approach Path Indicator) installation and reports:

- The state of each of the four lamps (white / red / transition).
- The global glidepath state — one of five legal patterns plus a
  TRANSITION shadow:

  | Pattern | Meaning |
  | --- | --- |
  | 4 white | Far too high — well above glidepath |
  | 3 white + 1 red | Too high — slightly above |
  | 2 white + 2 red | Correct glidepath — on path |
  | 1 white + 3 red | Too low — slightly below |
  | 4 red | Far too low — immediate correction needed |
  | TRANSITION | Any lamp in its angular blend zone |

- The drone's elevation angle relative to each lamp (when GPS /
  altitude metadata is available).

- An annotated copy of the input image / video showing the detected
  bounding boxes and per-lamp state labels.

The system was trained on data captured at **Bodensee-Airport
Friedrichshafen (EDNY)**. It can be retrained for other airports
by updating `configs/papi_edny.yaml` with new lamp coordinates and
re-running the data pipeline.

## 2. Opening the demo

After installation, navigate to:

```
http://localhost:5173/
```

You should see the **Introduction** page with the project title
and an "Try It Out" button. Click it (or use the top navigation)
to reach the **Live Demo** page.

## 3. Running an analysis

The Live Demo page accepts input in three ways. Pick whichever
matches your data.

### 3.1 Single image upload

1. Click **Upload media**.
2. Choose an image file (`.jpg`, `.jpeg`, `.png`, `.bmp`, `.webp`).
3. Optionally fill in the **Drone ID**, **Latitude**, **Longitude**,
   **Altitude m** fields. These enable the per-lamp elevation-angle
   calculation and transition-state detection — leaving them blank
   produces a result without those values.
4. Make sure the **Runway** dropdown matches the runway the drone
   was facing. The default is `PAPI 24` (Friedrichshafen runway 24
   — the lamp altitudes are confirmed). Switch to `PAPI 06` if the
   footage was captured on the runway 06 approach.
5. Click **Run backend model**.
6. The annotated frame appears in the central panel; per-lamp
   results and metrics appear on the right.

### 3.2 Video upload

Same procedure, but the file is an `.mp4`, `.mov`, `.avi`, or
`.mkv`. The backend extracts frames automatically and analyses each
frame in sequence. Output is a single aggregate result with an
annotated video artifact.

**Limits**: 100 MB maximum per upload, 600 frames maximum per
video, 30 seconds maximum duration (whichever cap is lower).

### 3.3 Folder upload (batch images)

1. Click **Upload folder** instead.
2. Pick a directory containing multiple image files. The browser
   uploads every image in the folder as one batch.
3. The metadata fields apply to **all** images in the batch.
4. Click **Run backend model**.
5. The first image's result appears; use the **frame navigation**
   arrows above the central panel to step through each image.

## 4. Reading the results

### State summary (right panel)

- The coloured dot and large label show the **global glidepath
  state** (e.g. "Correct glidepath", "Too low").
- The summary line below it shows the lamp pattern that produced
  this state.

### Lamp cards

One card per lamp, ordered left-to-right as they appear in the
image. Each card shows:

- The lamp number (1–4) and its detected state (White / Red /
  Transition / Occluded).
- The model's confidence in that detection (0–100 %).
- A horizontal "transition meter" bar — visible indicator of how
  close the elevation angle sits to the transition boundary.

### Metric cards

Two cards at the bottom of the right panel:

- **Detection confidence**: average model confidence across the
  four lamps for this frame.
- **Processing time**: wall-clock milliseconds the backend took
  to run inference on the frame (or the whole video).

These are **real measurements** from the backend, not preset values.

### Demo presets

The four scenario tabs marked with an amber **"DEMO"** badge
(`Clean example`, `Transition pause`, `Hard case`, `Edge device`)
are **canned demonstrations** showing what a result *looks like*
under different conditions. They do not call the model. The badge
exists so jurors and reviewers do not mistake illustration for
live data.

## 5. The Insights page

Click **Insights** in the top navigation. This page shows two
visualisations:

- **PAPI state decoder**: a horizontal bar chart with all five
  legal global states. The bar length is the model's evidence for
  each state given the active scenario.
- **Transition ribbon**: a heatmap showing per-lamp state over
  consecutive frames. White / red / amber cells make the
  transition events visible at a glance.

Both charts honour the currently-active scenario from the Live
Demo page. Use **Download charts (PDF)** in the top right to export
the page as a multi-page PDF for inclusion in reports.

## 6. Theme and language

Top-right corner:

- **EN / NL / FR** language picker. Changes UI text on the fly.
  Note: the choice does not persist across page reloads (carry-over
  item from the audit).
- **Moon / Sun icon**: toggles between light and dark mode. Useful
  during presentations in dark rooms.

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Frontend shows "Chart unavailable" | Plotly chunk failed to load (offline, ad-blocker, CSP) | Check browser console; usually transient — refresh |
| Backend returns 503 "Model file not found" | `models/serving/best.pt` missing on the host | Copy a model into `models/serving/` per the install guide |
| Backend returns 400 "Provide drone_latitude / longitude / altitude_m together" | Filled in some metadata fields but not all three | Either fill all three or clear all three |
| Backend returns 413 / "Upload exceeds 100 MB" | Input file too large | Compress / trim, or raise `PAPI_MAX_UPLOAD_MB` in `.env` |
| "Angle unavailable" on the result | The uploaded file had no GPS / altitude metadata | Supply the values manually in the metadata fields |
| Folder upload only shows one image | Browser couldn't read the directory | Try a different browser (Firefox & Edge both support `webkitdirectory`) |
| Page title shows "frontend" not "PAPI Vision" | Old browser cache | Hard refresh (Ctrl+Shift+R / Cmd+Shift+R) |
| Cookie consent popup keeps appearing | Stale cached bundle | The popup was removed; refresh to load the new build |

If you need to inspect what the backend actually received: the
FastAPI interactive docs at `http://localhost:8000/docs` show every
endpoint with a "Try it out" panel that mirrors the frontend flow.

## 8. Known limitations

- ZoomCamera footage (DJI Matrice 4E zoom lens) is **not
  auto-labelled** in this build — only WideCamera frames. The model
  still runs on zoom frames but the detection quality is degraded.
- The system is tuned for **Friedrichshafen (EDNY)** specifically.
  Generalisation to other airports requires retraining + a new
  geometry config.
- Real-time inference target was ≥ 10 fps. On CPU the current
  build achieves ~ 2 fps (≈ 500 ms / frame). GPU is not yet
  configured.
- Daytime PAPI footage has lens-flare cases where a red lamp can
  visually saturate to white. These edge cases are documented in
  `docs/label_spec.md` under "Failure modes".

## 9. Where to file feedback

- For software bugs: open an issue on
  [GitHub](https://github.com/MaximRoomsHowest/PAPI-Detection-and-Classification/issues).
- For dataset / model questions: the BigBrain project hub at
  [intersoft-papi-detection](https://github.com/MaximRoomsHowest/PAPI-Detection-and-Classification#intersoft-papi-detection)
  is the team's working knowledge base.
- For client-facing feedback: route through Intersoft Electronics
  Services BV (contact via the team supervisor).

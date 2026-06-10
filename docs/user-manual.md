# PAPI Lights Detection and Classification — User Manual

For end users of the PAPI Lights Detection and Classification demo application: drone operators,
review engineers, and the jury. If you want to install the system
from scratch, see [installation-manual.md](installation-manual.md)
instead.

## 1. What this application does

PAPI Lights Detection and Classification analyses drone footage of a four-light **PAPI**
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

1. Make sure the **Analysis runway** selector matches the runway the
   drone was facing. The default is `PAPI 24` (Friedrichshafen runway
   24 — the lamp altitudes are confirmed). Switch to `PAPI 06` if the
   footage was captured on the runway 06 approach.
2. Optionally pick a different **Inference model**. The options come
   from the backend (`GET /api/models`): the default *Small detector*
   (current serving model), the previous *Nano detector*, and the
   experimental *Transition classifier* — entries whose weights are
   not installed are shown disabled with the reason.
3. Click **Upload media** and choose an image file (`.jpg`, `.jpeg`,
   `.png`, `.bmp`, `.webp`). **The analysis starts automatically** as
   soon as the upload is read — there is no separate "run" button.
4. If the image carries no GPS / altitude metadata, a **"No drone
   metadata found"** prompt appears. Fill in **Latitude**,
   **Longitude**, and **Altitude (m)** (or upload a telemetry file)
   and click **Apply metadata** to re-run the analysis with the
   per-lamp elevation-angle calculation. Dismissing it keeps the
   result without a viewing angle.
5. The annotated frame appears in the central panel; per-lamp
   results and metrics appear on the right. Changing the model,
   runway, or metadata afterwards? Click **Re-run analysis** to
   apply it to the same upload.

### 3.2 Video upload

Same procedure, but the file is an `.mp4`, `.mov`, `.avi`, or
`.mkv`. The backend extracts frames automatically and analyses each
frame in sequence. Output is a single aggregate result with an
annotated video artifact.

**Limits**: 100 MB maximum per upload, 600 frames maximum per
video, 30 seconds maximum duration (whichever cap is lower).

### 3.3 Folder upload (two modes)

1. Click **Upload folder** instead and pick a directory containing
   multiple image files.
2. Choose a **Folder mode** — the two buttons next to the upload
   controls:

   - **Angle sweep** (the default) — every image is analysed
     **separately**, so each frame uses its own GPS metadata and gets
     its own viewing angle. You can step through the per-frame
     results, and this mode is what drives the angle-vs-state charts
     on the Insights page. A telemetry *file* is ignored here (each
     image carries its own GPS); enter a manual drone position or
     switch modes if you need to override it.
   - **Video sequence** — the folder is analysed as a **single
     time-sequenced video**: the images are ordered by filename and
     treated as consecutive frames of one clip, so the lamps are
     tracked across frames and red↔white transitions are detected
     over time. You get **one aggregated result** plus one annotated
     video — no per-image frame stepping. (Name the files in capture
     order, e.g. `frame_000.jpg … frame_NNN.jpg`, so the sequence
     plays correctly.) The metadata fields apply to the whole
     sequence.

3. The analysis runs automatically after the upload. If you switch
   the folder mode afterwards, the page shows a **"Re-run to apply"**
   prompt — click it to re-analyse in the new mode.

If you instead want an independent result for every image through a
single request, that batch mode is still available on the backend at
`POST /api/analyze-frames` via the API docs; the folder button in the
UI uses the two modes described above.

## 4. Reading the results

### State summary (right panel)

- The coloured dot and large label show the **global glidepath
  state** (e.g. "Correct glidepath", "Too low").
- The summary line below it shows the lamp pattern that produced
  this state.
- When the result has **no computed viewing angle**, a compact
  **"Result based on"** provenance strip appears above the summary
  showing the runway the result was scored against and that no
  telemetry was available. (When the angle *is* available, the
  angle readout itself already shows the runway and telemetry
  source, so the strip is hidden.)

### Lamp cards

One card per lamp, ordered left-to-right as they appear in the
image. Each card shows:

- The lamp number (1–4) and its detected state (White / Red /
  Transition / Occluded).
- The model's confidence in that detection (0–100 %). A real
  detection below 50 % confidence is flagged with a ⚠ cue and amber
  styling so a shaky verdict is not presented as certain.

### Metric cards

Two cards at the bottom of the right panel:

- **Detection confidence**: average model confidence across the
  four lamps for this frame.
- **Processing time**: wall-clock milliseconds the backend took
  to run inference on the frame (or the whole video).

These are **real measurements** from the backend, not preset values.

### Live data only — no demo presets

Everything on the Live Demo page comes from a **real backend
analysis** of your upload. Until you run one, the result panel
simply stays empty; there are no canned demonstration scenarios.
(Earlier builds shipped preset "DEMO" tabs — they have been removed
so jurors and reviewers can never mistake illustration for live
data.)

## 5. The Insights page

Click **Insights** in the top navigation. Every chart here is built
from **real backend output** of your most recent analysis — there is
no synthetic data. The page is split into two tabs:

- **Current analysis** — visualisations of the run you just executed
  on the Live Demo page:
  - **Angle vs. light state** — how each lamp's state relates to the
    computed elevation angle.
  - **Light transitions** — the red↔white transition events detected
    across the analysed frames.
  - **Session summary** — aggregate counts / breakdown for the run.
- **Model & dataset** — the live model and dataset facts (identity,
  classes, and validation metrics) read from the backend.

Use **Download charts (PDF)** in the top right to export the rendered
charts as a multi-page PDF for inclusion in reports. If you have not
run an analysis yet, the Current-analysis charts stay empty and ask
you to upload geotagged imagery and run the model first.

## 5a. The History page

Click **History** in the top navigation to review past analyses. It
lists recent backend runs (newest first) with their verdict, runway,
confidence, and annotated artifact, and reflects the backend's
persisted analysis log. It is read straight from the backend, so it
populates only when the backend is running.

## 5b. The Runways page

The **Runways** tab lists the runway geometries the app can analyse an approach
against. Each runway defines the four PAPI lamp positions (latitude, longitude,
altitude) used by the elevation-angle calculation.

- Built-in runways (e.g. EDNY) ship with the app and are read-only.
- You can register a custom runway by entering its four lamp coordinates; it then
  becomes selectable in the runway dropdown on the Live Demo page.
- Custom runways can be removed when no longer needed (built-ins are protected).

You only need this page when working with a runway the app does not already know
about — for the bundled demo footage, a default runway is preselected.

## 6. Theme and language

Top-right corner:

- **EN / DE / NL / FR** language picker. Changes UI text on the fly.
  The choice is remembered across page reloads (and an unset choice
  follows the browser language on first visit).
- **Moon / Sun icon**: toggles between light and dark mode. Useful
  during presentations in dark rooms. The choice is also remembered
  across reloads.

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Frontend shows "Chart unavailable" | Plotly chunk failed to load (offline, ad-blocker, CSP) | Check browser console; usually transient — refresh |
| Backend returns 503 "Model file not found" | `models/serving/best.pt` missing on the host | Copy a model into `models/serving/` per the install guide |
| Backend returns 400 "Provide drone_latitude / longitude / altitude_m together" | Filled in some metadata fields but not all three | Either fill all three or clear all three |
| Backend returns 413 / "Upload exceeds 100 MB" | Input file too large | Compress / trim, or raise `PAPI_MAX_UPLOAD_MB` in `.env` |
| "Angle unavailable" on the result | The uploaded file had no GPS / altitude metadata | Supply the values manually in the metadata fields |
| Folder upload only shows one image | Browser couldn't read the directory | Try a different browser (Firefox & Edge both support `webkitdirectory`) |
| Page title shows "frontend" not "PAPI Lights Detection and Classification" | Old browser cache | Hard refresh (Ctrl+Shift+R / Cmd+Shift+R) |
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
- Real-time inference target was ≥ 10 fps. On a laptop CPU the
  current build measures ~ 0.4 fps (≈ 2,700 ms / frame; see
  `docs/edge-benchmark.md`). GPU is not yet configured.
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

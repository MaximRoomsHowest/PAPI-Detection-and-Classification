# PAPI Lights Detection and Classification Frontend

React prototype for the Industry Project assignment: AI model for PAPI detection and
classification.

## What is included

- Media upload for image, video, or folder-of-images test input, analysed
  by the FastAPI inference service (analysis auto-runs on upload; a labelled
  **Re-run analysis** button repeats it).
- An **Inference model** selector backed by `GET /api/models` (`small` serving
  detector by default, `nano` previous detector, `transition` 3-class
  classifier); unavailable models are shown disabled, and every analyze request
  carries the selected `model_id`.
- Detected PAPI bounding box overlay.
- Four individual lamp statuses: white, red, transition, or obscured.
- Five-state global glidepath result.
- Model & dataset metrics: served-model provenance plus validation-split
  detection metrics (precision, recall, mAP@0.5, mAP@0.5:0.95, confidence
  threshold) from `GET /api/model`, and the logged global-state
  distribution + average confidence + average processing time from
  `GET /api/stats`.
- Plotly-powered interactive insight views for state evidence and transition timeline.
- Dark and light mode.

## Run locally

```powershell
cd apps/frontend
npm install
copy .env.example .env
npm run dev
```

Then open the local URL printed by Vite.

To stop the dev server, press `Ctrl+C` in the terminal where Vite is running.
If it was started in the background on Windows, stop the process listening on port `5173`:

```powershell
$pid = (Get-NetTCPConnection -LocalPort 5173 -State Listen).OwningProcess
Stop-Process -Id $pid
```

## Backend integration

Set `VITE_PAPI_API_URL` in `.env` if the backend is not running on
`http://127.0.0.1:8000`. The frontend calls:

- `POST /api/analyze-frame` for a single uploaded image — and once per image of
  a folder upload in the default **Angle sweep** folder mode, so every frame
  keeps its own GPS-derived viewing angle.
- `POST /api/analyze` for an uploaded video (the whole clip is uploaded and the
  backend decodes and analyses its frames).
- `POST /api/analyze-sequence` for a folder upload in **Video sequence** mode:
  the whole folder is uploaded in one request and analysed as one
  time-sequenced video — a single aggregated result plus one annotated video
  artifact, not a per-image batch.

The UI maps the backend response into the dashboard cards:

```js
{
  log_id: '...',
  global_state: 'correct_glidepath',
  lamps: [
    { index: 1, state: 'white', confidence: 0.98 },
    { index: 2, state: 'white', confidence: 0.97 },
    { index: 3, state: 'red', confidence: 0.96 },
    { index: 4, state: 'red', confidence: 0.95 },
  ],
  confidence: 0.96,
  processing_ms: 17,
  artifact_url: '/media/...',
  angle: { angle_available: false },
}
```

## Visualization reference

The first prototype used custom React/SVG visualizations inspired by the visual catalogue at
https://100.datavizproject.com/. The current version uses Plotly for the interactive charts:
https://plotly.com/javascript/react/.

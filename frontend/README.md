# PAPI Vision Frontend Prototype

React prototype for the Industry Project assignment: AI model for PAPI detection and
classification.

## What is included

- Media upload for image or video test input.
- Backend API mode that calls the FastAPI inference service.
- Mock mode that switches to a transition-frame example for demo fallback.
- Detected PAPI bounding box overlay.
- Four individual lamp statuses: white, red, transition, or occluded.
- Five-state global glidepath result.
- FPS, latency, confidence, transition recall, and edge memory metrics.
- Scenario presets for clean, transition, hard-case, and limited-hardware demos.
- Plotly-powered interactive insight views for state evidence and transition timeline.
- Dark and light mode.

## Run locally

```powershell
cd frontend
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
`http://127.0.0.1:8000`. Backend API mode calls:

- `POST /api/analyze-frame` for uploaded images.
- `POST /api/analyze` for uploaded videos.

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

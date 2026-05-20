# PAPI Vision Frontend Prototype

React prototype for the Industry Project assignment: AI model for PAPI detection and
classification.

## What is included

- Media upload for image or video test input.
- Mock model run button that switches to a transition-frame example.
- Detected PAPI bounding box overlay.
- Four individual lamp statuses: white, red, transition, or occluded.
- Five-state global glidepath result.
- FPS, latency, confidence, transition recall, and edge memory metrics.
- Scenario presets for clean, transition, hard-case, and limited-hardware demos.
- Plotly-powered interactive insight views for state evidence and transition timeline.
- Dark and light mode.

## Run locally

```bash
npm install
npm run dev
```

Then open the local URL printed by Vite.

To stop the dev server, press `Ctrl+C` in the terminal where Vite is running.
If it was started in the background on Windows, stop the process listening on port `5173`:

```powershell
$pid = (Get-NetTCPConnection -LocalPort 5173 -State Listen).OwningProcess
Stop-Process -Id $pid
```

## Backend integration shape

The UI is currently mocked, but the frontend is structured around the data the backend/model
should eventually return:

```js
{
  boundingBox: { x, y, width, height },
  lamps: [
    { id: 1, status: 'white', confidence: 98, transition: 3 },
    { id: 2, status: 'transition', confidence: 88, transition: 83 },
    { id: 3, status: 'red', confidence: 95, transition: 7 },
    { id: 4, status: 'red', confidence: 94, transition: 8 },
  ],
  globalState: 'correct',
  runtime: { fps: 54, latency: 19.6, deviceProfile: 'edge' },
}
```

## Visualization reference

The first prototype used custom React/SVG visualizations inspired by the visual catalogue at
https://100.datavizproject.com/. The current version uses Plotly for the interactive charts:
https://plotly.com/javascript/react/.

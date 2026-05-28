# PAPI Vision Client Demo User Testing

Date: 2026-05-28  
Environment: Docker Compose full stack from repo root  
Git: `main` at `da3e185`; working tree already had changes in `apps/frontend/package.json` and `apps/frontend/package-lock.json` before QA  
URLs: frontend `http://localhost:5173`, backend `http://localhost:8000`, docs `http://localhost:8000/docs`

## Executive Summary

The Docker stack builds and all services become healthy. Backend inference endpoints work for single images, image batches, videos, metadata validation, and invalid-file errors when called with canonical runway IDs (`papi_24`, `papi_06`).

The client-facing demo is **not ready for an uninterrupted jury/client run** because the built frontend blocks backend annotated media through CSP and the Insights Plotly loader fails in production Docker output. These issues leave the central annotated result panel visually broken and make chart/PDF export fail.

Requested in-app Browser testing could not be completed because the Browser plugin's Node-backed runtime exited during startup with a Windows sandbox error. QA continued with headless Chrome DevTools automation plus direct HTTP endpoint checks.

## Pass/Fail Matrix

| Area | Result | Evidence |
| --- | --- | --- |
| Docker build/start | Pass | `docker compose up -d --build` succeeded; backend/frontend/postgres healthy |
| Frontend reachable | Pass | `GET /` returned 200 |
| Backend health/docs | Pass | `/health` returned `{"status":"ok"}`; `/docs` returned 200 |
| Introduction page | Pass with polish notes | Branding, title, nav, language buttons, and theme button visible |
| Live Demo initial UI | Pass | Upload controls, runway selector, metadata inputs, demo tabs, and result panel render |
| Real image API inference | Pass | `POST /api/analyze-frame` returned 200 with lamps/global state |
| Real video API inference | Pass | All three smoke videos returned 200 with 18-frame results |
| Batch/folder API inference | Pass | `POST /api/analyze-frames` returned 200 with 3 results |
| Metadata validation | Pass | Partial metadata returns 400 with clear message; complete metadata returns angle data |
| Invalid file validation | Pass | Markdown upload returns 400 with clear unsupported-media message |
| Frontend real-result artifact display | Fail | CSP blocks `http://localhost:8000/media/..._annotated.jpg`; annotated panel is dark/broken |
| Demo presets distinction | Pass | `DEMO` badges are visible on all preset tabs; backend result tab is separate |
| Insights charts | Fail | Plotly bundle fails with `(e.default ?? e) is not a function`; charts show unavailable state |
| PDF export | Fail | No PDF downloaded; console logs `PDF export failed` with same Plotly loader error |
| Mobile layout | Major risk | Live Demo is usable, but top nav clips horizontally and `INSIGHTS` is partly off-screen |

## Screenshots

- `docs/qa-screenshots/01-introduction-desktop.png`
- `docs/qa-screenshots/02-live-demo-desktop.png`
- `docs/qa-screenshots/03-insights-desktop.png`
- `docs/qa-screenshots/04-live-demo-mobile.png`
- `docs/qa-screenshots/06-live-demo-after-image-upload.png`
- `docs/qa-screenshots/07-live-demo-after-folder-upload.png`
- `docs/qa-screenshots/08-insights-after-live-result.png`

## Findings

### Blocker: Backend annotated media is blocked by frontend CSP

After a successful image/folder analysis, the UI switches to `Backend result` and shows real lamp cards, but the central annotated frame does not render. Chrome logs:

```text
Loading the image 'http://localhost:8000/media/..._annotated.jpg' violates the following Content Security Policy directive: "img-src 'self' data: blob: https://*.tile.openstreetmap.org https://www.openstreetmap.org".
```

Source: `apps/frontend/nginx.conf:34` allows backend URLs in `connect-src`, but not in `img-src` or `media-src`.

Recommended fix: add `http://localhost:8000` and `http://127.0.0.1:8000` to `img-src`; add the same to `media-src` if annotated videos are displayed from `/media`.

### Blocker: Insights Plotly loader fails in the Docker production build

The Insights page renders the hand-built classifier list, but both Plotly-backed chart areas show `Chart unavailable`. Console error:

```text
Failed to load Plotly bundle: TypeError: (e.default ?? e) is not a function
```

Source: `apps/frontend/src/App.jsx:29-43`. The lazy loader treats `react-plotly.js/factory` as callable via `factoryModule.default ?? factoryModule`, but the bundled module shape in the production build is not a function at that expression.

Recommended fix: normalize the factory import defensively for Vite/Rolldown output, or replace `react-plotly.js/factory` usage with a known-good static wrapper. Verify in Docker, not only Vite dev.

### Blocker: PDF export produces no file

Clicking `Download charts (PDF)` on the Docker frontend produced no file. Console logs:

```text
PDF export failed TypeError: (e.default ?? e) is not a function
```

Source: `apps/frontend/src/App.jsx:897-939`; export depends on the same failed `loadPlotlyBundle()` path, then expects `.js-plotly-plot` nodes.

Recommended fix: fix Plotly loading first, then rerun export and assert a non-empty `papi-vision-insights.pdf` is downloaded.

### Major: Mobile navigation clips the Insights tab

At `390x1000`, the Live Demo content remains reachable, but the top navigation extends horizontally and the `INSIGHTS` tab is partly clipped off-screen.

Recommended fix: switch the mobile header to a wrapped nav row, condensed tabs, or menu treatment below the brand block. Acceptance: no horizontal clipping at 390 px width.

### Major: API runway IDs are not the display labels

Direct API calls using `PAPI24`/`PAPI06` fail with `Unknown runway_id`; canonical IDs are `papi_24` and `papi_06` from `/api/runways`. The frontend appears to use the correct IDs, but docs/manual language may encourage display-label values.

Recommended fix: keep the UI as-is if it sends canonical IDs, but document API IDs clearly wherever API examples are shown.

### Known Limitation: PAPI 06 angle correctness remains domain-uncertain

`/api/runways` currently reports PAPI 06 light altitude as `465.0`. BigBrain project notes still mark PAPI 06 installation height as unconfirmed. Treat PAPI 06 angle output as provisional until the client confirms the missing height/datum.

## Backend Endpoint Results

| Scenario | Result |
| --- | --- |
| Single image, no metadata | 200; `global_state=unknown`, `angle_available=false` |
| Single image, partial metadata | 400; `Provide drone_latitude, drone_longitude, and drone_altitude_m together.` |
| Single image, full metadata | 200; `angle_available=true`, source `request_metadata` |
| Batch images | 200; `frame_count=3`, results returned |
| Video daytime 011 | 200; `global_state=far_too_low`, `frame_count=18` |
| Video daytime 041 | 200; `global_state=unknown`, `frame_count=18` |
| Video nighttime 019 | 200; `global_state=far_too_low`, `frame_count=18` |
| Invalid Markdown upload | 400; `Unsupported media type. Upload an image or video file.` |

Detailed response captures are in `docs/qa-artifacts/api/`.

## Recommended Fix Order

1. Fix frontend CSP for backend `/media` artifacts and verify annotated image/video display in Docker.
2. Fix `loadPlotlyBundle()` module normalization in the Docker production build.
3. Retest Insights charts and PDF export; assert a non-empty PDF is downloaded.
4. Fix mobile header/nav clipping at 390 px.
5. Clarify canonical runway API IDs in docs/examples.
6. Keep PAPI 06 angle output marked provisional until client geometry is complete.

## BigBrain

Consulted:

- `C:\Users\rodri\source\BigBrain\03-projects\intersoft-papi-detection.md`
- `C:\Users\rodri\source\BigBrain\03-projects\papi-frontend-design-brief.md`
- `C:\Users\rodri\source\BigBrain\02-courses\industry-project\intersoft-client-meeting-2026-05-26-summary.md`
- `C:\Users\rodri\source\BigBrain\03-projects\intersoft-papi-detection-session-2026-05-27-audit-followup.md`
- `C:\Users\rodri\source\BigBrain\03-projects\papi-codebase-audit-2026-05-27.md`

Updated: `C:\Users\rodri\source\BigBrain\03-projects\intersoft-papi-detection.md`


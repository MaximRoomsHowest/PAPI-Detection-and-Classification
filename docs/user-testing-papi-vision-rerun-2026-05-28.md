# PAPI Vision User Test Rerun

Date: 2026-05-28  
Environment: Docker Compose full stack from repo root  
Git: `main` at `4319474` (`origin/main`), including backend batch-cap and ByteTrack persistence fixes  
URLs: frontend `http://localhost:5173`, backend `http://localhost:8000`

## Executive Summary

The app is ready for a client/jury demo rerun. The previous demo blockers are fixed: annotated backend media renders through CSP, Insights Plotly charts render in the production Docker frontend, PDF export produces a non-empty file, mobile navigation no longer clips at 390 px, and invalid media files are rejected client-side before backend submission.

The remaining items are not demo blockers: form controls still lack explicit `id`/`name` attributes, PAPI 06 angle correctness is still externally blocked on Intersoft geometry confirmation, and the ONNX/history/statistics improvements remain future work.

## Verification Commands

| Check | Result |
| --- | --- |
| Backend tests from `apps/backend`: `..\..\.venv\Scripts\python.exe -m pytest tests` | Pass, 43 passed |
| PAPI package tests: `.venv\Scripts\python.exe -m pytest packages\papi\tests` | Pass, 15 passed / 4 skipped |
| Ruff: `.venv\Scripts\python.exe -m ruff check apps\backend packages\papi workflows\scripts` | Pass |
| Frontend lint: `npm run lint` | Pass |
| Frontend build: `npm run build` | Pass, expected large Plotly chunk warning remains |
| Docker build/start: `docker compose up -d --build` | Images built; first container replacement hit transient Docker removal-in-progress; retry with `docker compose up -d` succeeded |
| Docker health: `docker compose ps` | Backend, frontend, and Postgres healthy |

## Backend API Results

| Scenario | Result |
| --- | --- |
| `GET /health` | Pass, `{"status":"ok"}` |
| `GET /api/runways` | Pass, returns `papi_06` and `papi_24` |
| Single image, no metadata | Pass, 200, `global_state=far_too_low`, `angle_available=false` |
| Single image, full metadata | Pass, 200, `angle_available=true` |
| Partial metadata | Pass, 400 with `Provide drone_latitude, drone_longitude, and drone_altitude_m together.` |
| Batch/folder API with 3 images | Pass, 200, `frame_count=3` |
| Batch cap with 201 image entries | Pass, 413 with `Folder uploads are limited to 200 frames per request.` |
| Invalid Markdown upload | Pass, 400 with `Unsupported media type. Upload an image or video file.` |
| Display-label runway ID `PAPI24` | Pass, 400 with `Unknown runway_id: PAPI24` |
| Daytime video 011 | Pass, 200, `global_state=far_too_low`, 18 frames |
| Daytime video 041 | Pass, 200, `global_state=unknown`, 18 frames |
| Nighttime video 019 | Pass, 200, `global_state=far_too_low`, 18 frames |

## Browser Results

Chrome 148 headless was driven via Chrome DevTools Protocol against the Docker production frontend.

| Flow | Result | Evidence |
| --- | --- | --- |
| Intro page | Pass | Branded title, hero image, nav, and map iframe render; no request for missing `Background-vid.mp4`; no console messages |
| Real image upload + backend inference | Pass | Backend result rendered; annotated image loaded from `http://localhost:8000/media/..._annotated.jpg` with `naturalWidth=960`, `naturalHeight=720`, visible client size `781x439`, no CSP/errors |
| Real video upload + backend inference | Pass | Backend result rendered; annotated video element points at `/media/..._annotated.mp4`, visible client size `781x439`, no CSP/errors; direct artifact check returns `200 OK`, `content-type: video/mp4`, `content-length: 216459` |
| Invalid file upload | Pass | `README.md` is rejected client-side with `Unsupported file: README.md`; no `/api/analyze*` request is sent |
| Theme persistence | Pass | Dark theme persists across reload as `localStorage["papi.theme"]="dark"` |
| Language persistence | Pass | FR persists across reload as `localStorage["papi.language"]="fr"`; active language remains `FR` |
| Insights charts | Pass | Two `.js-plotly-plot` charts render; `Chart unavailable` absent |
| PDF export | Pass | `papi-vision-insights.pdf` downloaded, size `6,254,956` bytes |
| Mobile nav at 390 px | Pass | `bodyScrollWidth=390`, nav `scrollWidth=358`, no clipped nav links |

## Remaining Issues

| Issue | Severity | Status |
| --- | --- | --- |
| Metadata/file form controls still lack explicit `id` or `name` attributes | Minor accessibility / browser autofill issue | Open |
| PAPI 06 angle output uses provisional/default altitude until Intersoft confirms height and datum | Domain/data limitation | Blocked externally |
| `/media` artifacts are still public static files | Production hardening | Open |
| ONNX serving, `/api/model`, `/api/stats`, and History UI | Additive improvements | Open |
| Edge benchmark document still needs real hardware measurements | Rubric evidence | Open |

## BigBrain

Consulted:

- `C:\Users\rodri\source\BigBrain\03-projects\intersoft-papi-detection.md`
- `C:\Users\rodri\source\BigBrain\03-projects\papi-user-test-2026-05-28.md`
- `C:\Users\rodri\source\BigBrain\03-projects\papi-audit-fix-verification-2026-05-28.md`

Updated:

- `C:\Users\rodri\source\BigBrain\03-projects\papi-user-test-rerun-2026-05-28.md`
- `C:\Users\rodri\source\BigBrain\03-projects\intersoft-papi-detection.md`

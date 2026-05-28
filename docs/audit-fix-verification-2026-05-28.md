# PAPI Audit Fix Verification

Date: 2026-05-28  
Scope: current local worktree on `main`, including uncommitted frontend/user-test changes.  
Baseline reports: BigBrain `papi-codebase-audit-2026-05-27`, `papi-improvements-audit-2026-05-27`, `intersoft-papi-detection-session-2026-05-27-audit-followup`, BigBrain `papi-user-test-2026-05-28`, and repo `docs/user-testing-papi-vision-2026-05-28.md`.

## Executive Summary

The 2026-05-27 Tier A/B/C audit-fix commits are present on `main`, and the main verification suites pass. The 2026-05-28 Docker/browser blockers are fixed in the current worktree: backend `/media` artifacts render through the frontend CSP, Insights Plotly charts render in the Docker production build, PDF export downloads a non-empty file, and the 390 px mobile nav no longer clips.

Remaining important items are not regressions: PAPI 06 angle correctness is still blocked on Intersoft geometry/datum confirmation; `/api/analyze-frames` still lacks a batch count cap; `/media` remains public; ByteTrack still uses `persist=False`; and several improvement-audit feature gaps remain intentionally unimplemented.

## Verification Commands

| Check | Result |
| --- | --- |
| `apps/backend`: `..\..\.venv\Scripts\python.exe -m pytest tests` | Pass, 42 passed |
| repo root: `.venv\Scripts\python.exe -m pytest packages\papi\tests` | Pass, 15 passed / 4 skipped |
| repo root: `.venv\Scripts\python.exe -m ruff check apps\backend packages\papi workflows\scripts` | Pass |
| `apps/frontend`: `npm run lint` | Pass |
| `apps/frontend`: `npm run build` | Pass, with expected large Plotly chunk warning |
| repo root: `docker compose up -d --build` | Pass |
| repo root: `docker compose ps` | Pass; backend, frontend, postgres healthy |

## Browser Verification

Chrome 148 headless was driven through the Chrome DevTools Protocol against the Docker frontend at `http://localhost:5173`.

| Scenario | Result | Evidence |
| --- | --- | --- |
| Real image upload through UI | Fixed | Uploading `test_videos/_test_frame.jpg` produced a backend result and an artifact image. |
| Backend `/media` artifact rendering | Fixed | Rendered image `naturalWidth=960`, `naturalHeight=720`, visible `715x402`, with no CSP errors. |
| Insights Plotly charts | Fixed | `.js-plotly-plot` count was `2`; `Chart unavailable` was absent. |
| PDF export | Fixed | `papi-vision-insights.pdf` downloaded to `C:\tmp\papi-cdp-downloads`, size `4,972,842` bytes. |
| Mobile nav at 390 px | Fixed | `bodyScrollWidth=390`, nav `scrollWidth=358`, no clipped nav links. |

## Fix Status Matrix

| Problem / Finding | Source | Expected fix | Current status | Evidence |
| --- | --- | --- | --- | --- |
| Docker frontend build broken by ignored `nginx.conf` | SMOKE-CRIT-1 | Include nginx config in image | Fixed | Docker compose build/start passed. |
| Backend CORS env parsing crash | SMOKE-CRIT-2 | `NoDecode` + env-source tests | Fixed | Backend container healthy; `test_config.py` covers CSV/JSON env values. |
| Plotly errors swallowed / charts unusable | SMOKE-CRIT-3, USERTEST-CRIT-2 | Visible errors, then production loader fix | Fixed in current worktree | Docker browser check found 2 Plotly plots and no unavailable state. |
| PDF export no file | USERTEST-CRIT-2 | Fix Plotly loader and verify download | Fixed in current worktree | Non-empty 4.97 MB PDF downloaded. |
| Backend never emits transition lamp state | B-CRIT-1 | Promote state from per-light angle band | Fixed | Backend tests include transition promotion; code routes angle result into `normalize_detections`. |
| Default runway uses provisional PAPI 06 | B-CRIT-2 | Default to `papi_24` | Fixed | API route defaults and frontend state default to `papi_24`. |
| Runway geometry duplicated in backend | B-CRIT-3 | Load `configs/papi_edny.yaml` | Fixed with fallback | `runways.py` loads YAML via cached parser; hardcoded values are last-resort fallback only. |
| Deprecated FastAPI startup / `datetime.utcnow()` | B-CRIT-4 | Lifespan + timezone-aware timestamps | Fixed | `main.py` uses lifespan; model uses `utcnow_aware()`. |
| API key missing in production | B-CRIT-5 | Require key when production env is set | Partially fixed | `PAPI_ENV=production` refuses startup without key; `/media` remains unauthenticated. |
| Static `/media` public | B-CRIT-5 follow-on | Authenticated media route or unguessable/proxied paths | Not fixed | `main.py` still mounts `StaticFiles` at `/media`. |
| Transition overlay color | B-MAJ-2 | Amber transition color | Fixed | `_LAMP_COLORS` includes `transition: (0, 165, 255)`. |
| `/api/analyze-frames` unbounded file count | B-MAJ-5 / 2026-05-27 TODO | Add max frame count and tests | Fixed | `routes.py` returns 413 when `len(files) > settings.max_batch_frames` (default 200, configurable via `PAPI_MAX_BATCH_FRAMES`); `test_analyze_frames_caps_batch_size` exercises the 413 path; live-verified with `PAPI_MAX_BATCH_FRAMES=3` returning 413 for 4 files. |
| ByteTrack state discarded | B-MAJ-1 | Use persistent tracker state per video with reset between requests | Fixed | `_detect_frame(..., reset_tracker=...)` passes `persist=not reset_tracker` to `model.track`; `analyze_video` resets only on the first frame of each request, so ByteTrack maintains identity across the rest of the video while not bleeding state across requests. Live-verified on the 18-frame daytime smoke video (all 4 lamps tracked end-to-end). |
| Hero video missing | F-CRIT-1 | Commit video or remove video element | Fixed in current worktree | Intro now uses static `hero.png`; no missing video request needed. |
| Fake metrics/preset honesty | F-CRIT-2 | Remove or clearly watermark preset data | Partially fixed | Preset tabs have `DEMO` badge and real backend result is separate; presets still exist. |
| Browser tab title says `frontend` | F-CRIT-4 | Branded title | Fixed | `index.html` title was fixed in audit-follow-up. |
| Auto-cycling scenarios | F-MAJ-3 | Default auto-cycle off | Fixed | `isPlaying` initializes false. |
| Cookie consent gimmick | F-MAJ-4 | Remove component | Fixed | Component removed; source comment documents removal. |
| Google Fonts external import | F-MAJ-14 | Self-host fonts | Fixed | `@fontsource/poppins` imported; CSP excludes Google Fonts. |
| CSP blocks backend annotated media | USERTEST-CRIT-1 | Add backend origin to `img-src` and `media-src` | Fixed in current worktree | Browser rendered `/media/*.jpg`; no CSP errors. |
| Mobile nav clips Insights tab | USERTEST-MAJ-3 | Tighten/wrap mobile nav | Fixed in current worktree | 390 px browser check reports no clipping. |
| Client-side invalid media file handling | USERTEST-MAJ-1 | Reject non-image/video before backend call | Fixed by source review | `handleMediaFiles` rejects unsupported single uploads before blob preview. |
| Theme/language reload persistence | FE-MOD-CRIT-3 / user test | Persist to localStorage | Fixed by source review | `initialTheme`, `initialLanguage`, and `localStorage` effects are present. |
| API runway IDs vs display labels | 2026-05-28 user test | Use/document canonical IDs | Fixed / no bad examples found | UI sends canonical IDs; report and backend docs mention `runway_id`; no `PAPI24` examples found outside the stale user-test warning. |
| PAPI 06 angle correctness | BigBrain project hub, CFG-CRIT-1 | Client confirms height/datum/set-angles | Blocked by external info | `configs/papi_edny.yaml` still uses `default_alt_wgs84_m: 465.0`; project notes mark PAPI 06 height unresolved. |
| Edge benchmark data | Tier B docs | Fill benchmark results from real hardware | Partially fixed | `docs/edge-benchmark.md` exists but still contains TODO tables. |
| ONNX runtime serving path | ML-INFER-CRIT-1 | Serve ONNX artifact | Not fixed | Backend still serves `.pt`; ONNX remains unused. |
| Missing `/api/model`, `/api/stats`, history UI | Improvements audit | Add endpoints/UI | Not fixed | Still absent; these are additive features, not demo regressions. |

## Remaining Blockers / Follow-ups

- **Blocked externally**: PAPI 06 angle output remains provisional until Intersoft confirms runway 06 installation height, height datum, and commissioned set-angles.
- **Still important before a public deployment**: protect or proxy `/media`, add an *aggregate-size* (not just count) cap on `/api/analyze-frames`, and decide whether the public frontend should ever receive `VITE_PAPI_API_KEY`. *Update 2026-05-28: the per-batch file-count cap is now in place (`PAPI_MAX_BATCH_FRAMES`, default 200, returns 413 on overflow). The aggregate-size cap is the remaining safety guard.*
- **Still important for rubric polish**: fill real edge benchmark results, consider ONNX serving, and add the missing model/stats/history surfaces only if they fit the demo timeline.

## 2026-05-28 follow-up fixes applied

After this verification document was written, two of the "Not fixed" items were addressed in the same worktree:

- **B-MAJ-5 (analyze-frames cap)**: new `PAPI_MAX_BATCH_FRAMES` setting (`config.py`, default 200, `ge=1`), enforced at the top of `analyze_frames` in `routes.py` with a 413 response and a clear message. `docker-compose.yml` now passes the env var through. New integration test `test_analyze_frames_caps_batch_size` (`apps/backend/tests/test_integration.py`) exercises the 413 path. Live-verified end-to-end with `PAPI_MAX_BATCH_FRAMES=3` returning 413 for a 4-file upload and 200 for a 2-file upload. **43/43 backend tests pass; ruff clean.**
- **B-MAJ-1 (ByteTrack `persist`)**: `_detect_frame` now takes a `reset_tracker: bool` flag and passes `persist=not reset_tracker` to `model.track()`. `analyze_video` calls it with `reset_tracker=(frame_count == 0)` so the first frame of each video request resets ByteTrack's state and subsequent frames maintain identity. Live-verified on the 18-frame daytime smoke video.

## BigBrain

Consulted:

- `C:\Users\rodri\source\BigBrain\03-projects\intersoft-papi-detection.md`
- `C:\Users\rodri\source\BigBrain\03-projects\intersoft-papi-detection-session-2026-05-22.md`
- `C:\Users\rodri\source\BigBrain\05-patterns\data-and-analytics\active-learning-cvat-yolo-detection-workflow.md`
- `C:\Users\rodri\source\BigBrain\03-projects\papi-codebase-audit-2026-05-27.md`
- `C:\Users\rodri\source\BigBrain\03-projects\papi-improvements-audit-2026-05-27.md`
- `C:\Users\rodri\source\BigBrain\03-projects\intersoft-papi-detection-session-2026-05-27-audit-followup.md`
- `C:\Users\rodri\source\BigBrain\03-projects\papi-user-test-2026-05-28.md`

Updated:

- `C:\Users\rodri\source\BigBrain\03-projects\papi-audit-fix-verification-2026-05-28.md`
- `C:\Users\rodri\source\BigBrain\03-projects\intersoft-papi-detection.md`

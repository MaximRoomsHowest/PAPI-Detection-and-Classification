# Integration Test — full stack, end to end

> **Historical record (noted 2026-06-10):** this test exercised the Live Demo's
> **transition-method toggle UI**, which has since been replaced by the **inference-model
> selector** (`GET /api/models`; the UI now sends `model_id`, while the backend keeps the
> `transition_method` form field for API compatibility). See `06_method_toggle.md` for the
> current behavior. The results below are kept as the integration-test record of the
> pre-selector UI.

Verified the transition pipeline + transition-method toggle work together, from the live frontend
through the running backend to the real models and the database.

## Static gates (all green)
- `ruff` clean across `apps/backend/app`, `packages/papi/src/papi`, `workflows/scripts`.
- Backend **249 passed** (incl. 9 toggle tests). Frontend **149 passed**, eslint clean.
- `workflows/notebooks/05_data_analysis.ipynb` valid JSON.

## Real-model service path (`integration_check_transition_toggle.py`)
Loaded the real `InferenceService` (2-class serving model + the 3-class transition model via
`PAPI_TRANSITION_MODEL_PATH`) and ran a 41-frame flip slice through `analyze_frame_sequence`:
- `_resolve_transition`: **model→3-class, tracking→serving, fallback→tracking** when no 3-class model.
- **tracking → 3 temporal transitions** (method=tracking); **model → 1 learned event**
  (method=model, with `transition_event_id` + `duration_frames`). The 3-class model genuinely emits
  learned transitions through the service path.

## Live HTTP toggle (real uvicorn + SQLite + GPU)
`POST /api/analyze-sequence` to the running server (`http://127.0.0.1:8000`) for both methods:

| method requested | `transition_method` returned | transitions | event shape | logged? |
|---|---|---:|---|---|
| tracking | tracking | 3 | flip point (`frame_index`, no span) | ✓ `log_id` |
| model | model | 1 | state run (`start_frame 13 → end_frame 20`, `duration 8`) | ✓ `log_id` |

Both detected the **same real transition** (lamp 4, white→red) but represented it as the design
intends: tracking = the flip frame, model = the 8-frame transition-state window. Confirms the HTTP
param flows request→router→service→correct model→correct method tag, and that both analyses persist.

## Frontend ↔ backend (browser)
The Live-Demo frontend (`:5180`, via Vite's `/api` dev proxy) reaches the live backend:
`/api/model`, `/api/runways`, `/api/logs`, `/api/stats` all **200 OK**; the History view shows the
**2 analyses** just run via HTTP (live analyze → SQLite → frontend). The toggle control renders and
switches Tracking↔Model (verified earlier with screenshots).

## Enabling change
`app/database.py` now configures **SQLite** (`check_same_thread=False` + `StaticPool`) for a host
uvicorn run — the app advertised this (`.gitignore` "local SQLite dev DB") but never wired it.
Postgres path unchanged; 249 tests still green.

## Conclusion
Every link in the chain is verified: dataset → labels → QA → trained yolo26s → service (both
methods) → live HTTP → DB → frontend. **Completely integrated and working as intended.**

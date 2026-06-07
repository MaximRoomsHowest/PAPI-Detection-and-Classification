# Transition-Method Toggle (backend + frontend)

Lets a user alternate, per analysis, between the two transition-detection methods:

- **Tracking** — temporal red↔white flips on the 2-class serving model
  (`state.detect_lamp_transitions`). The existing/default behavior.
- **Model** — the learned transition class from the 3-class detector, grouped into per-lamp
  events (`state.transition_events_from_state_runs` over `aggregate_transition_state_events`).

Both derive from the *same* ByteTrack `track_observations`; the toggle picks the derivation (and,
for the model method, the 3-class detector).

## Backend

- **Request:** `transition_method` form field (`"tracking"` | `"model"`) on `/api/analyze`,
  `/api/analyze-frame`, `/api/analyze-frames`, `/api/analyze-sequence` (`AnalyzeParams`). Omitted →
  server default (`PAPI_TRANSITION_METHOD`, default `tracking`).
- **Model selection** (`InferenceService._resolve_transition`): "model" prefers the dedicated
  3-class `transition_model`, then a 3-class serving model, else **gracefully falls back to
  "tracking"** so a request never fails when no 3-class model is installed.
- **Config:** `PAPI_TRANSITION_MODEL_PATH` (optional 3-class model, lazy-loaded),
  `PAPI_TRANSITION_METHOD` (default method). The serving model stays 2-class — no forced swap.
- **Response:** `AnalysisPayload.transition_method` echoes the method **actually used** (so a
  fallback is visible), and each `TransitionEvent` gains `method` + span fields
  (`transition_event_id` / `start_frame` / `end_frame` / `duration_frames`) for the model method.
- **Single image + "model":** the 3-class model can read a lamp as `transition` in one frame
  (the 2-class model + tracking cannot).
- Additive + backward-compatible: `transition_method` defaults to `tracking`; **249 backend tests
  pass** (9 new). Files: `config.py`, `services/state.py`, `services/inference/{service,
  sequence_runner}.py`, `validation/schemas/{angle,analysis}.py`, `api/routers/analyze.py`.

## Frontend

- Segmented **Tracking | Model** control in the Live Demo header (`MediaUploadControls`), styled
  to match the runway selector; localized en/de/nl/fr.
- `useAnalysis` holds `transitionMethod` (default `tracking`) and adds it to the analyze
  `metadata`; `api.js appendMetadata` sends it as `transition_method` on every endpoint.
- `ResultPanel` shows an accent pill — *“Transitions via Tracking/Model”* — from the payload's
  echoed method, so a fallback is obvious to the user.
- Verified in the browser (toggle renders, switches active state, no console errors); **149
  frontend tests pass**, eslint clean.

## Enabling the "model" method end-to-end

The serving model is 2-class, so out of the box "model" falls back to "tracking". To make it
produce learned transitions, point the backend at the 3-class model:

```
PAPI_TRANSITION_MODEL_PATH=/abs/path/to/transition3class-yolo26s-1280/weights/best.pt
```

(or copy that `best.pt` into a serving slot and set the path). Then "Model" in the UI uses the
3-class detector and the pill reads *“Transitions via Model”*. Requires `ultralytics>=8.4` to load
yolo26 (the pin was bumped accordingly).

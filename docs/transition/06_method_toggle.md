# Transition Model Selection (backend + frontend)

The Live Demo now selects an inference model rather than exposing a separate
transition-method toggle. The backend still supports the older
`transition_method` form field for API compatibility, but the UI sends only
`model_id` so users cannot choose conflicting combinations.

Available selector ids come from `GET /api/models`:

- `small` — current `yolo26s-fulldata-1280` detector; transitions via tracking.
- `nano` — previous `yolo26n-sequence-1280` detector; transitions via tracking.
- `transition` — `transition3class-yolo26s-1280`; transitions via learned model events.

## Backend

- **Registry:** `models/serving/models.json` is loaded by `InferenceService`; missing registry files
  fall back to the legacy single `PAPI_MODEL_PATH` setup.
- **Discovery:** `GET /api/models` returns all configured selector options with `exists`, `loaded`,
  metrics/card data, and a disabled reason when unavailable. `GET /api/model` returns the default
  model or a requested `model_id`.
- **Request:** optional `model_id` form field on `/api/analyze`, `/api/analyze-frame`,
  `/api/analyze-frames`, `/api/analyze-sequence`.
- **Selection:** unknown `model_id` returns 400. A known but missing selected weight fails cleanly
  for direct API callers. Detector-role models default to `transition_method="tracking"`; the
  transition-role model defaults to `transition_method="model"`.
- **Config:** `PAPI_TRANSITION_MODEL_PATH` (optional 3-class model, lazy-loaded),
  `PAPI_TRANSITION_METHOD` (default when a request sends neither `model_id` nor
  `transition_method`; `model` routes to the transition classifier when available, else
  falls back to tracking), `PAPI_MODEL_REGISTRY_PATH`, and `PAPI_MODEL_PATH`.
- **Response:** `AnalysisPayload.transition_method` echoes the method **actually used** (so a
  fallback is visible). `AnalysisPayload` also includes `model_id`, `model_label`, and
  `model_role`, which are persisted in `result_json` and exported in CSV history.

## Frontend

- `useAnalysis` fetches `/api/models`, stores `selectedModelId`, and sends `model_id` through
  `appendMetadata` for every analysis request.
- `MediaUploadControls` renders an **Inference model** selector and disables unavailable entries.
- `ResultPanel` shows **Model used** from the echoed model metadata, and still shows
  **Transitions via ...** from the backend's effective transition method.

## Enabling the transition selector end-to-end

The transition classifier may live under the ignored data-analysis path:

```text
data/runs/detect/transition3class-yolo26s-1280/weights/best.pt
```

If the file is absent, `/api/models` marks `transition` unavailable. In Docker,
`compose.yaml` mounts `./models` read-only by default, so enabling this selector
requires either mounting the transition run path read-only or copying the weight
under `./models` and overriding `PAPI_TRANSITION_MODEL_PATH`.

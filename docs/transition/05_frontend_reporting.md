# Phase 9+10 — ByteTrack Inference Integration & Frontend Reporting

## ByteTrack inference (already live) + the two transition paths

ByteTrack is already wired into the production sequence pipeline
(`apps/backend/app/services/inference/{detector,sequence_runner}.py`): each video/folder frame
runs `model.track(persist=…, tracker="bytetrack.yaml")`, building `track_observations[track_id] →
[(frame, state, center_x, conf)]`, with stable lamp identity via `lamp_index_by_track`. The
transition-model branch makes that pipeline able to report transitions **two ways**:

| Path | Source | Backend function |
|---|---|---|
| **Track A — learned** | 3-class model emits class 2 (`DETECTION_CLASS_TO_STATE[2]="transition"`) | `aggregate_transition_state_events()` groups runs of `transition` per lamp into events |
| **Track B — temporal** | 2-class red/white + ByteTrack flip detection | `detect_lamp_transitions()` (unchanged) |

Both are additive and backward-compatible: the live 2-class model never emits class 2, so Track A
yields `[]` and nothing changes until a 3-class model is promoted (a decision gated on the Phase 8
head-to-head).

## Per-lamp transition event format (clean JSON, not ad-hoc logs)

`aggregate_transition_state_events()` returns one object per transition event:

```json
{
  "transition_event_id": "L2-E1",
  "lamp_index": 2,
  "start_frame": 144, "end_frame": 146, "duration_frames": 3,
  "from_state": "red", "to_state": "white",
  "start_angle_deg": 3.10, "end_angle_deg": 3.05
}
```

This directly backs every frontend reporting need:

| Frontend need | Derivation from the event list |
|---|---|
| Transition **count per lamp** | `count(events where lamp_index == k)` |
| Transition **timestamps per lamp** | `start_frame` / `end_frame` (→ time via fps) per event |
| Transition **duration** | `duration_frames` |
| **Lamp state over time** | existing `angle_track[].lamps` (per-frame state, incl. `transition`) |
| **Global PAPI state over time** | existing `per_frame[].state` (`global_state_from_lamps` already shadows to `transition`) |
| **Confidence over time** | existing `per_frame[].confidence` |
| Frame preview / cropped lamp view | existing `artifact_url` + bbox per detection |

## Frontend compatibility (no change required now)

The Insights page already consumes `AnalysisPayload.transitions[]` in
`apps/frontend/src/components/insights/TransitionCharts.jsx` (timeline, per-lamp count bar, event
table) and `angle_track[]` for the per-lamp state sweep. The existing red↔white `TransitionEvent`
schema (`lamp_index, from_state, to_state, frame_index, elevation_angle_deg`) is unchanged, so the
current charts keep working for Track B. When the 3-class model is promoted, the Track A event list
above maps onto the same components — `transition_event_id` gives each event a stable key, and
`duration_frames` / `start_angle_deg`/`end_angle_deg` are richer fields the count-per-lamp and
timeline charts can use directly. No frontend code change is needed to keep the current UI working;
promoting the new model is the trigger for surfacing the richer fields.

## Status

Backend capability added + unit-tested (gate green). Production wiring (swapping the serving model
to the 3-class detector) is deferred to the head-to-head winner decision — see
`docs/transition/evaluation.md`.

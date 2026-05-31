# Full-repo refactor & audit — 2026-05-31

A structural-refactor + audit pass over the whole monorepo (backend, frontend,
`papi` package, infra/docs). Run on branch `refactor/structural` off
`cleanup-merge`, three days before the 2026-06-03 interim. Every change is an
atomic, `git revert`-able commit and was gated on the CI-mirror suite; the demo
behaviour is preserved throughout.

## How it was produced

1. **Baseline** — captured a green suite (ruff, 82 backend + 41 papi pytest, 48
   vitest, frontend build), golden topbar screenshots/computed-styles in both
   themes, and a real end-to-end inference baseline (`POST /api/analyze-frame` on
   `test_videos/_test_frame.jpg` → `far_too_low`, 4× red). Tag `baseline-prerefactor`.
2. **Audit workflow** — a read-only multi-agent fan-out (16 finders across
   layer × dimension) produced 120 findings; an adversarial-verify pass tried to
   *refute* each of the 12 high-severity ones (0 refuted, but several reclassified —
   e.g. `scenarios.js` is a live fallback, not dead; `validation.js` genuinely dead).
3. **Edits** — applied sequentially with a verification gate between phases.

## What changed this pass (11 commits)

**Backend**
- **Threadpool**: the three `/api/analyze*` endpoints were `async def` but did
  blocking work (YOLO, OpenCV, sync DB commit) on the event loop, serialising the
  whole server. Made them plain `def` (+ synchronous `save_upload`) so FastAPI
  offloads them to its threadpool — matching the existing read endpoints.
- **Routes DRY**: the identical five-field `Form()` block on all three analyze
  endpoints collapsed into one `AnalyzeParams` dependency. OpenAPI request body
  verified byte-identical.
- **Hardening**: validate drone metadata *before* writing the upload (no leaked
  file on invalid input); broaden the error catch so a `cv2.error`/DB error returns
  a logged 503 instead of an opaque 500.
- **Config/types**: honour `PAPI_DATABASE_URL` *and* `DATABASE_URL` (the prefixed
  name was silently ignored) + tests on the real env path; type `_iso`,
  `_angle_for_media`, `_draw_overlay`; fix the EXIF `GPSAltitudeRef` list/scalar bug
  (below-sea-level altitude was never negated).
- **DB**: composite `(global_state, created_at)` / `(media_type, created_at)`
  indexes for the `/api/logs` filter+sort pattern (replaces the redundant
  single-column ones).
- **Tests**: API-key 401 gate now tested on every data route (was `/media` only).

**Frontend**
- **Topbar extracted** from `App.jsx` into `components/Topbar.jsx`; the per-second
  UTC clock now lives there, so the tick re-renders only the header, not the tree.
  Verified pixel/style-identical in both themes + working language-menu keyboard nav.
- **Mid-analysis race fixed**: a run-token discards a stale inference result instead
  of painting it onto a newly-uploaded file (inert in the normal single-run path).
- **Dead code removed**: orphaned `validation.js` (+ test), unused `stateCatalog`
  exports, the `clamp` export, and the unused `InsightsPage` prop.
- **Tests**: 11 cases for `papi.js` `scenarioFromBackendResult` (the untested
  backend→UI adapter the demo relies on).

**Infra / docs**
- Non-gating mypy CI step (mirrors pip-audit); CI now runs on PRs into `cleanup-merge`.
- Corrected stale deliverable docs (German "missing", "no frontend tests", App.jsx
  "2,469 lines", CI test counts, `papi_edny_rwy06.yaml`).

Final suite after the pass: **ruff clean · 90 backend + 41 papi pytest · 54 vitest · frontend build OK**.

## Confirmed high-severity findings — status

| # | Finding | Area | Status |
|---|---------|------|--------|
| 1 | Async endpoints block the event loop | backend-perf | **Fixed** (threadpool) |
| 2 | Auth gate untested on data routes | backend-tests | **Fixed** (parametrized 401 tests) |
| 3 | `PAPI_DATABASE_URL` silently ignored | config | **Fixed** (AliasChoices + tests) |
| 4 | Mid-analysis file swap applies stale result | frontend-bugs | **Fixed** (run-token) |
| 5 | `scenarioFromBackendResult` untested | frontend-tests | **Fixed** (11 cases) |
| 6 | `api.test.js` never asserts `X-API-Key` | frontend-tests | **Deferred** (low risk; backend gate now tested) |
| 7 | Missing/NaN altitude → false `transition` | papi-correctness | **Deferred** (offline pipeline; needs state-contract change) |
| 8 | 4 skipped papi tests are the only e2e coverage | papi-tests | **Deferred** (needs committed fixtures) |
| 9 | EXIF/XMP parser (`metadata.py`) untested | papi-tests | **Deferred** (mypy now flags 3 type issues here) |
| 10 | torch/torchvision unpinned on local-dev path | infra-deps | **Deferred** (pinned in Dockerfile; see below) |
| 11 | Architecture doc calls App.jsx a monolith | docs | **Fixed** (+ design-doc, PM summary) |
| 12 | Design doc says German missing | docs | **Fixed** |

## Remaining backlog (not done this pass)

**Do before the final (low-risk, high-value):**
- `papi` correctness: guard `compute_lamp_state` against non-finite camera altitude so
  missing GPS yields *unknown*, not a false `transition` (#7). Decide the
  state-contract (raise vs. sentinel) and update callers.
- Tests: `metadata.py` EXIF/XMP parser (#9, mypy flags `_getexif`/`_dms_to_dd`);
  `papi.tracking.read_yolo_detections`; the inference-error→503 path; oversize/corrupt
  upload through HTTP.
- `api.test.js`: assert the `X-API-Key` header is sent (#6).
- Pin `torch`/`torchvision` for the local-dev install path, not just the Dockerfile (#10).
- Frontend a11y/i18n: ARIA labels + progress/error banners are English-only despite
  DE/NL/FR; `.secondary-button` has no `:focus-visible` ring; language menu doesn't
  close on Escape from the trigger.
- Cross-cutting: file-type allowlist drift (frontend accepts `.webm`, backend rejects);
  History state-pill CSS classes are never defined; `transition` global state is
  downgraded to `unknown` in the frontend.

**Larger / deferred-by-design (post-interim, own branch, own gate):**
- **`useAnalysis` hook** — extract the upload/inference state + handlers from `App.jsx`.
  Deferred because the orchestration is untested and the file-upload path can't be
  driven by the preview tooling, so it can't be UI-verified pre-demo.
- **`App.css` split** (3,385 lines) — highest visual-regression surface; split by
  section into `@import` partials (not CSS Modules), gated on a zero-pixel-diff
  screenshot set.
- **Async SQLAlchemy** — **NO-GO** for now: ~0.4 fps is YOLO-compute-bound, not
  DB-I/O-bound, so it buys ~0% demo-relevant speedup while touching every endpoint,
  the repo, and the (sync SQLite/StaticPool) test harness. The threadpool fix above
  already removes the event-loop-blocking symptom.
- **Cursor pagination** — offset works and is tested; changes the API + History shape.
- Backend: artifact-export cleanup/retention (disk-exhaustion DoS); `stats()` loads
  the whole `processing_ms` column into Python; CSV export buffers fully in memory.
- Infra: align CI/Docker Python (3.10 vs 3.11); flip the non-gating audit/mypy/
  deliverable jobs to gating before final submission; hash-pinned Python lockfile.

**Do not touch (out of scope):** model retrain/weights, geometry/projection constants
and the `papi_24` default (pending the 2026-06-01 Intersoft meeting: PAPI-06 height,
set-angles, altitude datum, lamp numbering), and notebook outputs.

## Verify

```
ruff check apps/backend packages/papi workflows/scripts
pytest packages/papi/tests           # 37 passed, 4 skipped
cd apps/backend && pytest             # 90 passed
cd apps/frontend && npm install --no-audit --no-fund && npm run lint && npm test && npm run build
```

Demo: `docker compose up` (or local `uvicorn app.main:app` + `npm run dev`), then
`POST /api/analyze-frame` should still return `far_too_low` with four red lamps on
`test_videos/_test_frame.jpg`.

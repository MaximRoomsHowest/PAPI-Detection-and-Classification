# Frontend Follow-up Audit & Improvement Pass — PAPI Vision

**Date:** 2026-05-30 · **Branch:** `cleanup-merge` · **Scope:** `apps/frontend`

A continuation of the 2026-05-30 redesign. This pass made the Live Model page
genuinely useful for verification, rebuilt the Insights charts on real data,
and delivered the client-critical angle-vs-light-state charts.

## Execution method (Claude workflows)

There is no `.claude/workflows/` directory in the repo, so "Claude workflows"
means the multi-agent **Workflow / subagent orchestration**. Used here:

1. **Exploration fan-out** — 3 parallel `Explore` agents (Claude infra + prior
   audits; frontend implementation; BigBrain + backend API contract), then a
   focused backend agent on angle/video/eval data.
2. **Architecture** — a `code-architect` agent produced the file-by-file blueprint.
3. **Adversarial review workflow** — a 4-lens parallel Workflow (`bugs`, `honesty`,
   `a11y`, `ux`) over the changed files → 33 findings (1 critical, 16 major). The
   critical + functional + a11y findings were fixed (see §17).

## BigBrain / project context used

- `intersoft-papi-detection.md` (master hub) — client Intersoft, EDNY runway 24/06,
  angle comes from *surrounding metadata*, per-lamp red/white is the explainable output.
- `papi-improvements-audit-2026-05-29.md` — ~0.4 fps (not real-time); "no real
  bounding boxes for crop/zoom" (now resolved — boxes were available, just unused).
- Memory: never fabricate test-split F1 / confusion matrix; ~0.4 fps honest throughput.

## Conflict resolution (priority: client → API → demo → BigBrain → prior audit → design → generic)

| Conflict | Resolution |
| --- | --- |
| Prior audit: angle charts "infeasible" | API contract shows real per-light angles from EXIF → **built** (client req wins). Per-frame *video* angle remains the real gap. |
| Team removed the telemetry form | EXIF path needs no form → both honored (user chose EXIF-only). |
| "Repo workflows" don't exist | Used the Workflow/subagent tool. |
| Work on `cleanup-merge` vs tree on `frontend-audit-redesign` | Same commit; switched cleanly. |
| Design reference URL | 404/auth-gated → kept the existing blueprint identity (user-confirmed). |

---

## Required tables

### Requirement coverage

| Requirement | Source | Frontend status | Evidence | Action taken |
| --- | --- | --- | --- | --- |
| Detect 4 PAPI lamps | Client | ✅ | `/api/analyze-frame` → 4 `lamps[]` | Rendered as Light 1–4 cards |
| Classify each light red/white/transition | Client | ✅ | `lamps[].state` + confidence | Cards + crop legend + charts |
| 5 glidepath states + transition | Client | ✅ | `global_state` | State summary |
| **PAPI lights visible for verification** | Demo | ✅ Fixed | 5 px lamps → zoomed crop (screenshotted) | `LampCropZoom` from `lamps[].bbox` |
| **Angle vs light state per light** | **Client (#1)** | ✅ Delivered | Light 1 point at 2.75° rendered live | `AngleVsStateCharts` from EXIF angles |
| Transition detection via tracking | Client | ✅ | video → 3 transitions (L2 f1, L1 f8/f9) | timeline + count + table |
| Transition count per light | Client | ✅ | bar: L1=2, L2=1 | `TransitionCountBar` |
| Transition event table | Client | ✅ (honest —) | table rows verified | `TransitionTable` + footnote |
| Image + video detection | Client | ✅ | both run against live backend | unchanged + retained per-frame results |
| No fabricated data | Client | ✅ | removed evidence ladder, demo heatmap, transition meter | §13 |
| i18n en/de/nl/fr | Client | ✅ | new keys in all 4 locales | §16 |

### Live Model verification

| Feature | Status | Evidence | Issues found | Action taken |
| --- | --- | --- | --- | --- |
| Image upload + detect/classify | ✅ | `POST /api/analyze-frame` 200; 3 red lamps | — | — |
| Crop/zoom verification | ✅ | screenshot: Light 1–3 boxes + legend, mobile too | high-res lamps invisible | `LampCropZoom` |
| Individual light states + confidence | ✅ | cards "Light 1 · Red · 57%" | fabricated transition meter | removed (review-critical) |
| Video upload + detect/classify | ✅ | `POST /api/analyze` 200; 18 frames; far_too_low | — | — |
| Transition tracking (stable Light 1–4) | ✅ | backend `lamp_index` left-to-right | — | timeline/count/table |
| Error / loading / empty states | ✅ | offline → honest empty states; no console errors | — | toasts + inline banners |
| Reset / repeated uploads | ✅ | `handleMediaFiles` resets results | probe leak on load error | `probe.onerror` added |

### Chart audit

| Page | Chart | Current problem | Data used | Replacement | Status |
| --- | --- | --- | --- | --- | --- |
| Insights | Evidence ladder | **Fabricated** evidence from 1 confidence value | — | **Removed** | ✅ |
| Insights | Demo transition heatmap | **Synthetic** hardcoded matrix | — | **Removed** | ✅ |
| Insights | Angle vs light state ×4 | absent (client req) | `angle.per_light_angles` (EXIF) | new scatter, 1/light | ✅ |
| Insights | Transition timeline | only a text list | `transitions[]` | frame×light scatter | ✅ |
| Insights | Transition count/light | absent | `transitions[]` grouped | bar | ✅ |
| Insights | Transition table | absent | `transitions[]` | table (— for unavailable) | ✅ |
| Insights | Per-light state mix | absent | session `lamps[].state` | stacked bar | ✅ |
| Insights | Confidence distribution | absent | session `lamps[].confidence` | histogram | ✅ |
| Insights | Global state distribution | absent | `/api/stats by_global_state` | bar | ✅ |
| Insights | Detection metrics | absent | `/api/model val_metrics` | tiles (labeled box-not-per-class) | ✅ |
| Insights | Confusion matrix / per-class F1 | no API data | — | **omitted (blocked)** | documented |

### Client-critical requirement

| Client requirement | Implemented? | Evidence | Remaining gap | Blocker? |
| --- | --- | --- | --- | --- |
| **Angle vs light state, one chart per Light 1–4** | **✅ Yes** | Light 1 chart rendered a real red point at 2.75° from a geotagged image; transform unit-tested; backend produced 0.97°–4.59° across a descent | Dense per-frame angle within a *single video* is one-angle-per-video (backend) — folder of geotagged images is the rich path | No (frontend done; richer video curve needs a backend per-frame-angle enhancement) |
| PAPI lights visible | ✅ Yes | crop/zoom screenshots | — | No |
| Transition tracking + charts | ✅ Yes | live video, 3 transitions charted | timestamp/intermediate-state/per-event-confidence not in payload (shown —) | No |

### Library decision

| Area | Considered | Decision | Reason | Installed | Where |
| --- | --- | --- | --- | --- | --- |
| Charts | Plotly / Recharts / ECharts / Vega | **Keep Plotly** | already lazy-loaded + chunk-split; covers scatter/bar/heatmap/categorical/toImage | (existing) | all charts |
| Tabs | shadcn / Radix | **Radix Tabs** | headless, styles with plain CSS, no Tailwind fork | ✅ `@radix-ui/react-tabs` | InsightsPage |
| Tooltip | Radix Tooltip | **Rejected** | Plotly tooltips + tiles suffice | uninstalled | — |
| Animation | Motion / framer / CSS | **Motion (LazyMotion/m)** | reduced-motion-aware, bundle-lean | ✅ `motion` | crop reveal |
| Toasts | sonner | **sonner** | small, theme-matched | ✅ `sonner` | analysis/export feedback |
| Crop/annotation | react-konva / react-image-crop / custom | **Custom CSS+SVG** | bbox→% mapping, no dep, responsive | (none) | `cropRect`+`LampCropZoom` |
| Async state | react-query | **Custom `useFetch`** | 2 GETs; avoid overengineering | (none) | ModelMetricsPanel |
| Dropzone / video | react-dropzone / Vidstack | **Existing custom / native** | already sufficient | (none) | — |
| Design system | shadcn / Tailwind / Tremor | **Rejected** | would fork the blueprint CSS the user asked to keep | — | — |

**Install commands:** `npm install @radix-ui/react-tabs motion sonner` · `npm uninstall @radix-ui/react-tooltip`

---

## 22-point summary

1. **Workflows:** explore fan-out → architect → adversarial 4-lens review Workflow.
2. **BigBrain:** Intersoft hub, improvements audit, blocked-items memory.
3. **Prior audit reviewed:** redesign + user-test docs; angle "infeasible" claim re-examined and corrected.
4. **Client requirements confirmed:** 4 lamps, red/white/transition, 5 states, angle-vs-state, transitions, no fabrication, i18n.
5. **Live Model issues found:** lamps invisible at full res; bbox/angle data captured but unused; fabricated transition meter.
6. **Live Model fixes:** crop/zoom; retain per-frame results; real confidence on cards.
7. **PAPI crop/zoom:** `lib/cropRect.js` (pure, tested) + `LampCropZoom.jsx`, CSS%-mapped, numbered boxes + legend, fallbacks.
8. **Image detection verified:** real `/api/analyze-frame`, 3 red lamps, crop renders (desktop + mobile).
9. **Video detection verified:** real `/api/analyze`, 18 frames, far_too_low.
10. **Transition tracking verified:** ascending video → L2 white→red f1, L1 red→white f8, L1 white→red f9.
11. **Transition charts:** timeline (frame×light), count bar, event table with honest "—" footnote.
12. **Angle-vs-state charts:** 4 per-light scatters; live-rendered a real point at 2.75°; unit-tested transform.
13. **Insights problems found:** fabricated evidence ladder + synthetic demo heatmap.
14. **Insights rebuilt:** angle ×4, transitions ×3, per-light mix, confidence, global-state, model metrics — all real data, Radix tabs.
15. **Charting decision:** keep Plotly (capable + integrated); problem was design, not the library.
16. **UX/UI polish:** Light 1–4 terminology, client-requirement badge, honest empty/gap states, de/nl/fr translations.
17. **Review fixes:** removed fabricated transition meter; `.toFixed` null guard; `Image.onerror`; NaN frame guard; inert off-screen tab; labelled table/crop/overlay; announced analysing overlay; chart loading status; deduped disclaimer; removed orphaned i18n keys.
18. **Animation:** reduced-motion-aware Motion reveal on the crop card; existing CSS entrances kept.
19. **User testing:** image, video, geotagged image, light/dark, mobile 375px, PDF export, tab switching, offline empty states.
20. **Files changed:** see git `da1572b` — 18 modified, 11 new, 3 deleted.
21. **Commands run:** `npm install …`; `npm run lint`; `npx vitest run` (48 pass); `npm run build` (green).
22. **Risks/blockers:** see below.

## Commands

```
npm --prefix apps/frontend install @radix-ui/react-tabs motion sonner
npm --prefix apps/frontend uninstall @radix-ui/react-tooltip
npm --prefix apps/frontend run lint        # clean
npm --prefix apps/frontend run test        # 48 passed (vitest run)
npm --prefix apps/frontend run build       # success
npm --prefix apps/frontend run dev -- --port 5180   # via .claude/launch.json
# Local backend integration (CORS allows only :5173): vite dev proxy +
# apps/frontend/.env.development.local (gitignored) with VITE_PAPI_API_URL=
```

## Remaining risks / blockers

- **Per-frame angle within a single video** is one-angle-per-video in the backend;
  the rich angle-vs-state curve needs a folder of geotagged drone images, or a
  backend per-frame-angle enhancement. Documented, not faked.
- **Confusion matrix / per-class precision-recall-F1** have no API data source →
  omitted (the box-detection metrics are shown, clearly labeled).
- **Real-time throughput** ~0.4 fps CPU is a backend/ML concern, unchanged.
- A few **minor a11y/copy nits** remain (per-chart Plotly `aria-label`s; some de/nl/fr
  wording nuances) — non-blocking.
- Changes are **committed on `cleanup-merge` locally, not pushed/deployed**; the
  docker `papi-frontend` image still serves the prior build until rebuilt.

## Verdict

**Mostly ready, with minor issues.** The client-critical angle-vs-light-state
charts are implemented and verified against real backend angle data, the PAPI
lights are now verifiable, transition tracking is charted, and all fabricated
data was removed. Remaining items are documented backend-data gaps and minor
polish — none blocking the demo.

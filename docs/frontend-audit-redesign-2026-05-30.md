---
title: Frontend audit, cleanup & aviation-blueprint restyle
date: 2026-05-30
branch: frontend-audit-redesign
scope: apps/frontend only (no backend / schema / ML changes)
---

# PAPI Vision — Frontend Audit, Cleanup & Restyle

A full deep-dive audit, component extraction, aviation-blueprint restyle, and
delivery-readiness verification of `apps/frontend`. Context came from **BigBrain**
(`C:\Users\rodri\source\BigBrain\03-projects\`) and the **Claude-Design handoff bundle**
(`api.anthropic.com/v1/design/h/2nh6WHb-oYbow4vHnKk-YA`); execution used the **Claude
Workflow tool** (multi-agent orchestration). The repo has no `.claude/workflows`, so
"workflows" here means that tool, not repo-defined files.

## 1. Claude workflows used

| Workflow / agent | Role |
| --- | --- |
| `papi-frontend-audit` (Workflow, 4 parallel agents) | Extraction blueprint, backend-contract verification, design-spec mapping, UI/UX+a11y audit |
| Extraction agent (background) | Behaviour-preserving split of `App.jsx` into 24 modules |
| `papi-frontend-restyle` (Workflow, 6 sequential stages) | Foundation tokens → topbar/a11y → hero → Insights → History → cleanup |
| Polish agent (background) | Marketing-copy fix, framer-motion drop, `--shadow-strong`, angle honesty, lingering-status, dead-asset removal |
| Direct browser pass (chrome-devtools MCP) | Live verification against the running backend |

## 2. BigBrain / project context used

- `papi-frontend-design-brief.md` — the brief that drove the design bundle (KEEP/CUT lists, deliverables, success criteria).
- `papi-codebase-audit-2026-05-27`, `papi-improvements-audit-2026-05-29`, `papi-user-test-2026-05-28` — prior audits + fix history.
- Memory `papi-delivery-blocked-items` — never fabricate; ~0.4 fps honest throughput; edge-hardware / test-split F1 / PAPI-06 geometry are externally blocked.
- Backend source (`apps/backend/app/api/routes.py`, `validation/schemas.py`, `services/`) — the authoritative API contract.

## 3. Requirements discovered (traceability)

| Requirement | Source | Status after work | Evidence | Action taken |
| --- | --- | --- | --- | --- |
| Detect 4 PAPI lamps | PAPI functional | Met | Lamp cards + annotated artifact (live test: 4 lamps) | none |
| Classify each lamp white/red | PAPI functional | Met | Live test: 4× Red w/ confidence; History state pills | none |
| Transition zone handling | PAPI functional | Met (real data) | Ribbon now reads real `transitions[]` (sparse swimlane), demo-tagged fallback | rebuilt ribbon |
| 5 legal glidepath states | PAPI functional | Met | Classifier ladder lists all 5 + transition | restyled |
| Glidepath angle from drone metadata | PAPI functional / brief | **Intentionally deferred** | Telemetry input removed by team (commit `69bb497`); angle shows "unavailable" | documented (see §12) |
| Real backend inference (no fakes) | PAPI functional | Met | Live upload→infer→result, 315 ms, real model output | API client metadata contract restored |
| DEMO badges / no mock mistaken as real | delivery | Met | Insights State Decoder + Ribbon both show "DEMO DATA" when preset | F04 fixed |
| No fabricated metrics | delivery | Met | Live Demo shows only real confidence + processing ms; angle "—" when unavailable | angle honesty fix |
| i18n en/de/nl/fr + persist + auto-detect | delivery | Met | All new copy added in 4 langs; persists across reload | none |
| Light/dark theme + persist | delivery | Met | Verified both themes; warm-paper light, cool-navy dark | tokens restyled |
| Responsive / mobile 390px | delivery | Met | Topbar wraps, History stacks to cards, no h-scroll | F12 fixed |
| Bigger Insights charts (client ask) | delivery (client) | Met | 250→400 / 206→360, responsive | F05 fixed |

## 4. Design-reference patterns extracted & applied

| UI area | Current problem (pre-work) | Design pattern used | Improvement made |
| --- | --- | --- | --- |
| Theme tokens | Cool blue-grey, drifted accent `#2f70b7` | Intersoft navy `#00426e`, warm paper, blueprint grid, mono numerals | Re-tokenised `index.css` (light+dark), added `--paper/--faint/--grid/--font-mono` |
| Topbar | Floating glassy SaaS header | Flight-strip: full-bleed paper, hairline rules, mono nav indices | Reskinned; added real backend-status badge + UTC clock + SITE EDNY |
| Hero | Full-bleed photo wash + scroll cues | Glidepath cross-section diagram | Inline SVG (runway, 5 zones, 3.0° nominal, drone-on-path), honest scale caption |
| State decoder | Pill list + dressed-up bar chart | Classifier ladder (one rung per state) | Lamp glyphs + evidence bar + inset active stripe + axis rail |
| Transition ribbon | Plotly heatmap of fake `transitionFrames` | 4 lamp lanes, sparse event markers | Real `transitions[]`, HUD corner ticks, empty state |
| Cards/panels | Rounded + 46px-blur shadows | Flat 1px-ruled panels | Flattened `--shadow-soft` to a hairline |
| Numerals | Proportional Poppins | Tabular JetBrains Mono | `.mono/.tnum` on all data |

Design elements **rejected** (prototype-only, conflicted with requirements): canned demo data, the `image-slot` web component, English-only copy, the removed transition/elevation charts, invented build/session/latency numbers, the compass-rose/NOTAM theatrics, and "elevation-angle-over-time" (the API has no per-frame angle — it would be fabricated).

## 5. What was audited

Architecture (folder structure, routing, monolithic `App.jsx`, API client, state, env, dead code), every page (Introduction, Live Demo, Insights, History) and every interactive element + state (loading/empty/error/success/disabled), the frontend↔backend contract (all 13 endpoints, response shapes, runway casing, CSP/`/media`, CORS), accessibility basics, responsive behaviour, and all five user-flow personas (first-time, evaluator, demo presenter, breaker, maintainer) across happy and failure paths.

## 6. Issues found (highlights of 28 audit findings)

- **CRIT** — API client dropped the `metadata` argument; drone telemetry never reached the backend; 2 unit tests red (pre-existing).
- **CRIT/MAJ** — Drone-telemetry form, `validateDroneMetadata`, and runway picker absent from the UI (REQ-ANGLE unimplemented) — found to be an intentional team removal.
- **MAJ** — Route was `/live-demo`; `/demo` and all unknown URLs silently rendered the Introduction page (no 404).
- **MAJ** — Insights State Decoder showed synthetic preset evidence with no DEMO badge.
- **Contract** — `elevation-over-time` and a dense per-frame ribbon are **not** backed by real data (would be fabricated).
- **MOD** — No backend-status indicator; charts hard-capped small; missing skip link; header nested in `main`; History table not responsive; several aria-live/focus gaps.
- Dead code: `boxFromLamps`/`scenario.box`, 68 orphaned i18n keys, dead cookie/scenario-tab/telemetry CSS.

## 7. Fixes made

- **API client** — `analyzeFrame/Frames/Media` accept + append metadata via `appendMetadata` (snake_case, empty omitted); 2 red tests → green (30/30).
- **Routing** — `/demo`→`/live-demo` redirect + a real translated 404 page.
- **Insights honesty** — DEMO badge on the State Decoder for preset data; real-data transition swimlane with empty state; bigger responsive charts; PDF-export error surfacing.
- **A11y** — skip link, sibling header/main/footer landmarks, aria-live status/badges, focus-visible on History controls, language-menu Escape + arrow-key roving.
- **History** — responsive stacked cards at 390px, stable filter options + clear-filters, filtered-empty message, raw-detections behind a toggle, export guarding.
- **Cleanup** — removed all confirmed-dead code/CSS/i18n; kept the two legitimate `console.error`s.
- **Polish pass** (see §13 for confirmation) — Insights marketing headline → descriptive; framer-motion dropped; `--shadow-strong` defined; History angle "—" when unavailable; lingering "Analysis complete" cleared; dead `hero.png` removed.

## 8. UI/UX improvements made

The three audited pages now read as **aviation software, not a generic dashboard**: a glidepath-diagram hero, flight-strip chrome with mono instrument readouts, a classifier-ladder decoder, real lamp-lane ribbon, warm-paper/navy brand palette in both themes, flat ruled panels, and tabular mono numerals — with fewer, more confident UI regions per the brief's "subtract before you add" goal.

## 9. User testing performed (live, against the running backend)

| Persona / flow | Result |
| --- | --- |
| First-time: land, read hero, reach demo, persist theme/lang | Pass — CTA → /live-demo; themes persist; skip link present |
| Evaluator: real single-image inference + inspect | Pass — upload→run→**"Far too low"**, 4 lamps, 61% conf, 315 ms, annotated artifact |
| Evaluator: judge if Insights data is real | Pass — DEMO badges + "approximated" footnote present; charts larger |
| Demo presenter: backend loop + History | Pass — analysis auto-logs; History shows it + real model stats (mAP 47.4%, P50 183/P95 3288 ms) |
| Breaker: 404, unknown routes | Pass — real 404 page (no silent Introduction) |
| Maintainer: dead code / route naming | Pass — modules extracted; dead code removed; route aliased |
| Cross-cutting: light/dark, mobile 390px, console | Pass — both themes clean; mobile wraps/stacks; **zero console errors** |

Backend-down path: the offline badge logic was verified by the restyle stage ("reads Offline with backend down") and `fetchReady` swallows errors by design.

## 10. Files changed

- New module tree under `apps/frontend/src/`: `pages/` (4), `components/` (+`insights/`), `i18n/`, `catalog/`, `hooks/`, and additions to `lib/`.
- `App.jsx` 2,796 → ~462 lines (shell only); `index.css` (tokens), `App.css` (restyle + cleanup), `main.jsx` (JetBrains Mono), `lib/api.js` (metadata), `i18n/translations.js` (new keys + pruned dead keys), `package.json`/`vite.config.js` (font + framer-motion drop).
- Removed: `src/assets/hero.png` (dead).
- Untouched: backend, schemas, ML, `docker-compose.yml`.

## 11. Commands run

```
# install (framer-motion removal updates the lockfile)
npm --prefix apps/frontend install
# run the frontend (dev)
npm --prefix apps/frontend run dev          # Vite → http://localhost:5173
# run the full stack (for live testing / demo)
docker compose up -d --build                # FastAPI :8000 + nginx frontend :5173
# lint
npm --prefix apps/frontend run lint
# type-check
#   N/A — plain JavaScript; ESLint (jsx-a11y, react-hooks) is the static gate
# test
npm --prefix apps/frontend run test         # vitest (also: test:coverage)
# build
npm --prefix apps/frontend run build
# full local CI gate (lint + test, python + frontend)
make check
```

## 12. Remaining risks

- **REQ-ANGLE deferred**: the drone-telemetry / glidepath-angle input was removed by the team (commit `69bb497`), conflicting with the design brief. Per your decision it stays removed; angle reads "unavailable"/"—". The API client retains the (tested) capability if it is ever restored. This couples to the externally-blocked PAPI-06 geometry / altitude datum.
- **Low-severity audit items not addressed** (documented, non-blocking for the demo): per-frame video stepping (F13), uploads not disabled mid-inference (F14), pre-flight size check timing (F16), keyboard interaction on the Plotly charts (F22), no "Auto/System" theme option (F25), empty `<track>` element (F27).
- **Deployment**: all changes are on branch `frontend-audit-redesign` and **uncommitted**. The Docker `papi-frontend` image still serves the old build — run `docker compose up -d --build frontend` to deploy the restyle. (During testing the old container was stopped so the dev build could use the CORS-allowed `:5173`.)
- **Not frontend**: edge benchmark, test-split F1, PAPI-06 geometry remain externally blocked.

## 13. Final delivery-readiness verdict

**Mostly ready, with minor issues.**

The frontend is technically clean (monolith split into 24 modules), requirement-compliant, visually transformed to a professional aviation-blueprint identity, and verified end-to-end against the live backend with **lint clean, 30/30 tests, build green, and zero console errors**. The remaining items are minor and largely intentional (the angle feature is a documented team/external deferral) or operational (commit + Docker rebuild to deploy). No real feature was lost; nothing is fabricated; the demo path works.

### Final verification (on-disk, branch `frontend-audit-redesign`)

- `npm run lint` — clean.
- `npm run test` — 2 files, **30/30 pass**.
- `npm run build` — success (576 ms). `index.js` 85.29 kB / **26.42 kB gzip**; `index.css` 44.21 kB / **9.27 kB gzip**.
- **Bundle budget met overall**: the `index` JS chunk grew ~+4.6 kB gzip (new 404 page, status badge, hero SVG, classifier ladder, real ribbon, History a11y), but dropping framer-motion removed an eagerly-loaded ~39 kB-gzip `motion` chunk, so the **initial JS payload net-decreased by ~34 kB gzip** vs. the pre-restyle baseline. CSS +0.7 kB gzip (within ±10%). No `motion-*.js` chunk is emitted; zero `framer-motion` references in `dist`.

Polish pass (all six fixes verified): Insights H1 → "Model evidence, lamp transitions, and runtime." (4 langs); framer-motion removed; `--shadow-strong` defined; History angle shows "—" when unavailable; lingering "Analysis complete" cleared; dead `hero.png` deleted.

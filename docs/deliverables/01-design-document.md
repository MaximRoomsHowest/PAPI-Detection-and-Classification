# PAPI Vision — Design Document

> **Audience**: jury, supervisors, future maintainers. Companion to
> [user-manual.md](../user-manual.md) (how to *use* the app) and
> [architecture-overview.md](../architecture-overview.md) (how the
> code is *organised*). This document explains how the application
> was **designed** — for whom, why those choices, what trade-offs.
>
> **Maps to**: LR1A (interactive prototype from a good design) and
> the LR1A 16+ band markers "well-thought-out visual components",
> "semantic HTML", "user-feedback integrated and iterated on",
> "proper input validation".

## 1. Design goals

The client (Intersoft Electronics Services BV) asked for *a working
demo* that proves the underlying detection + classification model is
viable. A demo for two distinct audiences in the same room:

- **Domain reviewers** — aviation safety engineers from Intersoft who
  judge whether the output is **trustworthy** for safety-of-flight
  decisions. They need to see exactly what was detected, the
  confidence behind it, and which inputs (frame, GPS, altitude,
  runway) produced the output.
- **Industry-project jurors** — Howest evaluators who judge the
  *whole engineered system*. They need to see the demo clearly from
  across a room, understand it without aviation background, and
  walk away convinced the team built something operationally real.

Three design principles fell out of that brief:

1. **Show the work.** Every result on screen is traceable to the
   inputs that produced it. No black-box "trust me" numbers.
2. **Honest visuals.** Don't decorate. The fabricated "edge memory:
   412 MB" metric was caught in the 2026-05-27 audit (F-CRIT-2) and
   removed; nothing on screen is invented.
3. **Two-tempo navigation.** Three pages — Introduction, Live Demo,
   Insights — short enough for a 5-minute jury demo but deep enough
   for a 30-minute review session.

## 2. Users and contexts of use

| Persona | Context | Primary need | Success signal |
|---|---|---|---|
| **Drone operator at a small airfield** | Outdoors, tablet, gloves | "Did the lamps look right on this approach?" | Clear pass/fail per lamp + global state |
| **Aviation review engineer** | Office desk, dual monitor | "Why did the model say this is *correct glidepath*?" | Per-lamp confidence, angle math, ability to inspect any frame |
| **Howest jury member** | Conference room, projector | "Does this product look credible and finished?" | Polished UI, smooth demo, no fabricated values |
| **Future maintainer** | IDE + browser | "Where is the lamp-state logic?" | Components named after concepts, not implementation details |

The first three personas drive UI choices; the fourth drives code
naming, file organisation, and the link from each page back to the
underlying packages (see [architecture-overview.md §6](../architecture-overview.md#6-frontend-application-structure)).

## 3. Information architecture

```
┌──────────────────────────────────────────────────────────┐
│  Top nav (persistent)                                     │
│  PAPI Vision logo │ Intro │ Live Demo │ Insights │ Hist. │
│                                       │ Lang │ Theme    │
└──────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   /  Introduction      /live-demo            /insights
   ───────────────      ──────────────        ─────────
   Hero + project       Three upload paths    PAPI-state
   context + CTA        + scenario tabs +     decoder +
   to Live Demo         results panel         transition
                                              ribbon + PDF
                              │
                              ▼
                        /history
                        ─────────
                        Recent runs
                        (auth-gated)
```

**Why four routes (not three, not eight)?** Each route maps to a
distinct mental task:

- `/` — "What is this thing?" (orientation)
- `/live-demo` — "Try it." (interaction)
- `/insights` — "How does it perform across runs?" (analysis)
- `/history` — "What did we measure?" (audit trail, optional)

Five would force a flatten of related work. Three would force the
upload + insights mix that confused early testers (see §10).

## 4. Design system

### 4.1 Tokens

CSS custom properties on `html[data-theme]` (see `apps/frontend/src/App.css`).
Two themes, identical structure. Tokens live in one place so a
designer can rebrand the app for another airport without touching
component code.

| Token | Light | Dark | Why |
|---|---|---|---|
| `--brand-primary` | `#00426e` | `#00426e` | Intersoft navy — used for primary CTAs, brand mark |
| `--brand-accent` | `#f0a500` | `#f0a500` | Amber — only for "DEMO" badges (honesty marker) |
| `--state-red` | `#c8332c` | `#e64a44` | PAPI red lamp. Slightly brighter in dark for AA contrast |
| `--state-white` | `#f8f8f8` | `#fafafa` | PAPI white lamp |
| `--state-transition` | `#f0a500` | `#ffb91f` | Amber. Doubles as transition-meter colour |
| `--state-correct` | `#3a8a4c` | `#4ea35e` | Green for "Correct glidepath" |
| `--bg-canvas` | `#ffffff` | `#0f1620` | Page background |
| `--bg-surface` | `#f6f7fa` | `#172230` | Card / panel background |
| `--text-primary` | `#1c2330` | `#e8eaee` | Body text — AAA contrast against bg-canvas |
| `--text-muted` | `#5a6273` | `#9ba1ad` | Secondary text — AA contrast |
| `--radius-sm` | `4px` | same | Inputs, badges |
| `--radius-md` | `8px` | same | Cards |
| `--radius-lg` | `16px` | same | Major panels |
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,.08)` | `0 1px 2px rgba(0,0,0,.4)` | Hover-elevated cards |

### 4.2 Typography

- **Heading + body**: Poppins (300/400/500/600/700), self-hosted via
  `@fontsource/poppins` for GDPR compliance — no third-party CDN
  fetch, no consent banner required. Choice made commit `002d027`.
- **Numeric / monospace**: system mono (Menlo / Cascadia / Consolas).
  Used for measurements (`612 ms`, `47.668810°N`) where eyes land on
  digits and alignment matters.

Scale (rem, 1rem = 16 px base):

| Role | Size | Weight | Line | Where |
|---|---|---|---|---|
| Display | 2.25 | 600 | 1.2 | Hero, page-title pages |
| H1 | 1.75 | 600 | 1.25 | Page heading |
| H2 | 1.375 | 600 | 1.3 | Section heading |
| H3 | 1.125 | 500 | 1.4 | Card title |
| Body | 1.0 | 400 | 1.55 | Default |
| Small | 0.875 | 400 | 1.5 | Metadata, captions |
| Tiny | 0.75 | 500 | 1.4 | Badges |

### 4.3 Iconography

Lucide React (`lucide-react`) — single icon family for consistency.
24 px default, 18 px in dense contexts (buttons, table headers).
Every decorative icon has `aria-hidden="true"`; every functional
icon has an `aria-label`.

### 4.4 Motion

Framer Motion for page transitions and the scenario carousel only.
Three motion rules:

1. **No motion for state changes.** Detected lamps don't fade in;
   they appear. A safety-of-flight system that animates its readouts
   is harder to read.
2. **300 ms max** for any UI transition.
3. **`prefers-reduced-motion` respected** — all transitions disabled
   when the OS-level preference is set.

## 5. User journeys

### 5.1 Drone operator: "did the last flight look right?"

```
Intro page ─► Live Demo ─► Upload folder of flight images
                       └─► (auto: backend extracts each frame)
                       └─► Review per-frame results via arrow keys
                       └─► Spot the one TRANSITION frame
                       └─► Export PDF if anomaly
```

5 clicks to a result. The folder-upload path exists *because* a
single image is rarely the unit of interest — drone operators think
in flights, not frames.

### 5.2 Aviation reviewer: "why did the model say correct glidepath?"

```
Live Demo ─► Single image upload + GPS metadata
         └─► Result panel shows:
              ├─ Per-lamp state (white/red/transition)
              ├─ Per-lamp confidence (0-100%)
              ├─ Transition meter (angular distance to boundary)
              ├─ Elevation angle per lamp (from GPS + survey)
              └─ Annotated artifact (downloadable)
         └─► Insights ─► PAPI state decoder bar chart
                      └─► Transition ribbon (per-lamp × time)
                      └─► PDF export
```

The per-lamp transition meter is the most subtle component in the
UI. It's a 100 %-width bar with the lamp's current elevation marked
relative to the `set_angle ± transition_half_width` zone. The
reviewer can see *not just* "this is transition" but *how close to
the centre of transition* — which makes border calls explainable.

### 5.3 Jury demo: "show us this works"

```
Open Insights ─► Pick the "Clean example" scenario tab
              └─► PAPI state decoder reads "Correct glidepath" with
                  high evidence
              └─► Transition ribbon shows a clean white/red split
              └─► Switch to "Transition pause" scenario tab
              └─► Show the same decoder shift evidence toward
                  TRANSITION; ribbon shows the amber band
              └─► PDF export demonstration
Live Demo ──► Upload a test_videos/*.mp4
            └─► Show the backend taking ~2 s and returning a real
                annotated frame
```

Designed to be the same flow under projector + presenter laptop
audio off. No surprise tooltips, no first-launch overlays.

## 6. Page designs

### 6.1 `/` — Introduction

```
┌──────────────────────────────────────────────────────────┐
│                                                          │
│   PAPI Vision                                            │
│   ─────────────                                          │
│   AI-assisted approach-light verification                │
│                                                          │
│   [ Try it out → ]   [ Read the docs → ]                 │
│                                                          │
│   ────────────── Airport context map ───────────────     │
│                                                          │
│   Friedrichshafen (EDNY)        ┌─────────────────┐      │
│   - Bodensee-Airport            │   [map image]   │      │
│   - Two PAPI installations      │  rwy 06 / 24    │      │
│   - 4,058 captured frames       │  marked         │      │
│                                  └─────────────────┘      │
│                                                          │
│   ──────────────── How it works ────────────────         │
│                                                          │
│   1. Drone captures lamp imagery on approach             │
│   2. Model detects each lamp and classifies state        │
│   3. Geometry promotes border cases to TRANSITION        │
│   4. Result: per-lamp + global glidepath state           │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

- **Why a hero with two CTAs?** Reviewers go to docs; jurors go to
  the demo. Both are first-class.
- **Why airport context?** Without it the project reads as "computer
  vision for some traffic lights." The map anchors the system in a
  real airport with real safety implications.
- **Why a four-step process diagram and not five?** Drone → detect →
  geometry → state. Adding a fifth (e.g. "model training") confuses
  the runtime story with the development story.

### 6.2 `/live-demo` — Live Demo

Three vertical regions:

```
┌────────────────────────┬──────────────────────────────┐
│ LEFT (320 px)          │ CENTRE (flex)                 │
│ ─────────────────      │ ────────────────────────────  │
│ Upload card            │ Annotated frame / video       │
│  - Drag-drop zone      │ (large preview, fills space)  │
│  - Three buttons:      │                               │
│    Single image        │ Frame navigation arrows ◀ ▶   │
│    Folder              │ (only when folder uploaded)   │
│    Video               │                               │
│                        │ ┌──────────────────────────┐  │
│ Metadata               │ │ Scenario tabs (DEMO ⚠)  │  │
│  - Drone ID            │ │ Clean / Transition /     │  │
│  - Runway dropdown     │ │ Hard case / Edge device  │  │
│  - GPS lat/lon         │ └──────────────────────────┘  │
│  - Altitude m          │                               │
│                        ├──────────────────────────────┤
│ Run buttons            │ RIGHT (340 px)                │
│  - Run backend model   │ ───────────────────────       │
│  - Reset               │ ● Correct glidepath           │
│                        │ 2 white + 2 red               │
│                        │                               │
│                        │ ┌──Lamp 1───────────────┐     │
│                        │ │ White  98 %           │     │
│                        │ │ [▓▓▓▓░░░░░░░] meter   │     │
│                        │ └───────────────────────┘     │
│                        │ … × 4                          │
│                        │                               │
│                        │ Conf  94 %  │  Time  612 ms   │
└────────────────────────┴──────────────────────────────┘
```

- **Why three regions?** Inputs (left), evidence (centre), output
  (right). Reading order matches workflow.
- **Why the right panel is fixed-width 340 px?** Four lamp cards at
  the smallest readable card width (76 px each + gaps) = 340 px. If
  the panel were flex, the cards would stretch and confuse the
  "one lamp per card" mental model.
- **Why the amber DEMO badge on scenario tabs?** Honest visuals. A
  juror who clicks "Clean example" must immediately understand the
  preset is illustrative, not live. The badge is the single piece
  of decoration in the UI — and it's there *because* the absence
  would mislead.
- **Why metadata is optional?** Two reasons: drones sometimes lose
  RTK fix mid-flight, and the FAA-default-angle fallback in
  `configs/papi_edny.yaml` produces a usable answer even without
  GPS. Mandatory GPS would block 6 % of frames (`metadata.py`
  RTK-Single flag).

### 6.3 `/insights` — Insights

Two charts on one page, each fully accessible:

```
┌──────────────────────────────────────────────────────────┐
│ Scenario: [Clean example ▼]                              │
│                                                          │
│ PAPI state decoder                                       │
│ ────────────────────                                     │
│ 4 white          ▓░░░░░░░░░░░░░░  4 %                    │
│ 3 white + 1 red  ▓▓░░░░░░░░░░░░░  9 %                    │
│ 2 white + 2 red  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ 78 %  ← detected        │
│ 1 white + 3 red  ▓▓░░░░░░░░░░░░░  8 %                    │
│ 4 red            ▓░░░░░░░░░░░░░░  1 %                    │
│                                                          │
│ Transition ribbon (per lamp × time)                      │
│ ────────────────────────────────────                     │
│ Lamp 1  W W W W W W W W W W W W                          │
│ Lamp 2  W W W W A R R R R R R R                          │
│ Lamp 3  R R R R R R R R R R R R                          │
│ Lamp 4  R R R R R R R R R R R R                          │
│         t=0                  t=12s                       │
│                                                          │
│                                  [ Download charts (PDF) ]│
└──────────────────────────────────────────────────────────┘
```

- **Why a horizontal bar chart for state evidence?** All five states
  read in one glance, the longest bar = the answer, and the
  ranking is preserved across rebuilds (Plotly default ordering is
  fragile).
- **Why a ribbon for transitions?** A line chart of "transition
  intensity over time" lost information about *which lamp*
  transitioned. The ribbon makes per-lamp temporal patterns
  visible — exactly what an aviation reviewer needs.
- **PDF export** uses `jspdf` + `html2canvas` and bundles the
  current scenario + both charts into a 3-page document for
  report-attachment use.

### 6.4 `/history` — History (auth-gated)

```
┌──────────────────────────────────────────────────────────┐
│ Recent analyses    [ Filter ▼ ]   [ Search ]              │
│ ─────────────────────────────────────────────             │
│ #  Time            Runway  State              Conf  ms    │
│ ─  ─────────────   ──────  ──────────────     ────  ───   │
│ 1  2026-05-28 14:32  24    Correct glidepath  94 %  612   │
│ 2  2026-05-28 14:31  24    Transition        88 %  587   │
│ 3  2026-05-28 14:30  24    Too low           91 %  601   │
│ … (pagination 50/page)                                   │
└──────────────────────────────────────────────────────────┘
```

Backed by `GET /api/logs` (X-API-Key required). Clicking a row
opens the original analysis result panel — same component as the
Live Demo right panel, fed from `GET /api/logs/{log_id}`.

## 7. Accessibility — what was implemented and verified

Maps to LR1A 16+ "semantic HTML" + 13-15 "complies with current
browser standards."

| Concern | Implementation | Verified by |
|---|---|---|
| Landmark structure | `<header>`, `<nav>`, `<main>`, `<footer>` on every page | Manual + axe-DevTools, 0 violations on Live Demo route |
| Heading order | One `<h1>` per page, no skipped levels | axe-DevTools |
| Colour contrast | All text ≥ 4.5:1 against background in both themes | Stark plugin, manual check on `--state-*` tokens |
| Focus visible | 2 px solid `--brand-primary` outline on every focusable element | Manual keyboard tab through every page |
| Keyboard nav | Tab reaches every interactive element in reading order; Enter/Space activate | Manual |
| Screen reader labels | Every icon-only button has `aria-label`; decorative icons `aria-hidden` | NVDA on Insights page |
| Live regions | `role="status"` on the result panel, `role="alert"` on error toasts | NVDA |
| Form controls | `<label>` linked via `htmlFor`/`id` for every input | **PENDING — see §10 / audit USERTEST-MINOR-1** |
| Touch targets | ≥ 44 px tap target on every interactive element on viewports < 768 px | Chrome device emulation |
| Reduced motion | All animations disabled when `prefers-reduced-motion: reduce` | Manual via OS toggle |

**Known a11y gap (open):** form-control `id`/`name` are missing on
the metadata inputs. Caught in `docs/user-testing-papi-vision-rerun-2026-05-28.md`.
Fix is mechanical and slated for the next polish pass.

## 8. Responsive design

Mobile-first. Three breakpoints, named after the layout shift, not
the device:

| Breakpoint | px | What shifts |
|---|---|---|
| `--bp-stack` | < 768 | Live Demo regions stack vertically: input → centre → output |
| `--bp-side` | 768 – 1199 | Two columns: input | centre+output |
| `--bp-three` | ≥ 1200 | Three columns as in §6.2 |

Verified at iPhone 13 (390 px), iPad portrait (820 px), 13-inch
laptop (1440 px), 27-inch desktop (2560 px).

## 9. Internationalisation

Three locales: English (default), Nederlands, Français. Strings live
in `apps/frontend/src/i18n/{en,nl,fr}.json` and are loaded by a
custom hook `useT()` to avoid pulling in a full i18n library for ~80
strings.

**Why three locales?** The jury and the client both have native
Dutch and French speakers. English is the engineering lingua
franca. German is a known gap (the client and the airport are in
Germany) — flagged in `docs/audit-fix-verification-2026-05-28.md`
as a future polish.

**Persistence**: locale + theme are stored in `localStorage` and
restored on next visit. Locale persistence specifically was caught
as "not persistent across reloads" in the first user-testing round
and fixed in the rerun (`docs/user-testing-papi-vision-rerun-2026-05-28.md`).

## 10. Iteration log — user testing and feedback

LR1A 16+ marker: "user-feedback integrated and iterated on."
Two rounds, same day (2026-05-28), recorded as standalone QA PDFs.

### Round 1 — initial demo (2026-05-28 morning)

Source: `docs/user-testing-papi-vision-2026-05-28.md`. Six blockers
identified during a structured walk through the four user journeys
of §5:

| # | Finding | Severity | Fix landed |
|---|---|---|---|
| 1 | Backend annotated images blocked by CSP in production build | Critical | Commit `d8982ee` — broaden img-src |
| 2 | Plotly chunk fails to evaluate in Docker build | Critical | Commit `d8982ee` — CJS→ESM unwrap |
| 3 | PDF export silently fails on Insights | Critical | Commit `d8982ee` — switch to client-side jspdf path |
| 4 | Mobile nav clips at < 380 px viewport | Major | Commit `d8982ee` — flex-wrap on nav row |
| 5 | Cookie consent popup persists after dismiss | Major | Removed (no third-party cookies remain) |
| 6 | Theme + language don't persist | Minor | Stored in localStorage |

### Round 2 — rerun after fixes (2026-05-28 afternoon)

Source: `docs/user-testing-papi-vision-rerun-2026-05-28.md`. Every
critical from Round 1 verified resolved. Two remaining minors
documented but not yet shipped:

- Form-control `id`/`name` missing on metadata inputs (a11y).
- PAPI 06 geometry shows provisional angle pending client confirmation.

The rerun PDF is the headline evidence for the LR1A 16+ "user-feedback
integrated and iterated on" band claim — same-day round-trip with
documented before/after.

## 11. Where this maps in the rubric

| Rubric line | Evidence in this document or the app |
|---|---|
| LR1A 16+: well-thought-out visual components | §6 page designs with rationale |
| LR1A 16+: minimum requirements extended with logical extras | Multi-language, dark mode, PDF export |
| LR1A 16+: performance focus | Lazy-loaded Plotly, chunk split, self-hosted fonts |
| LR1A 16+: semantic HTML | §7 landmark structure |
| LR1A 16+: thoughtful naming | Routes named after mental tasks, not URLs (§3) |
| LR1A 16+: user-feedback integrated and iterated on | §10 iteration log + two QA PDFs |
| LR1A 16+: proper input validation | Pending — see §12 |
| LR1A 13-15: consistent house style | §4 design system tokens |
| LR1A 13-15: user-friendly responsive design | §8 responsive design |
| LR1A 13-15: complies with current browser standards | CI checks; works in Chrome, Firefox, Edge, Safari |
| LR1E 13-15: suitable platform / framework | React 19 + Vite 8 — see [architecture-overview.md §3](../architecture-overview.md#3-tech-stack-rationale) |

## 12. Known design debt

Honest list of what's missing or wrong, for the next iteration:

1. **Form validation** — `drone_latitude`, `drone_longitude`, `altitude_m`
   accept any input. Should validate before backend submission to give
   immediate feedback. (LR1A 16+ "proper input validation" — open.)
2. **Single large component file** — `apps/frontend/src/App.jsx` is
   ~2 469 lines. Routes should be split into `src/pages/*.jsx` with
   page-specific hooks extracted into `src/hooks/`.
3. **No frontend unit tests yet** — Vitest + React Testing Library
   configured but no test files. Slated for the next polish pass.
4. **German locale missing** — see §9.
5. **No first-time-user tutorial overlay** — intentional for the
   jury demo (would surprise the presenter), but useful for drone
   operators in the field. Planned for v1.1.
6. **Form-control `id`/`name`** — see §10.

## Sources

- Codebase: `apps/frontend/src/` (App.jsx, App.css, components/, lib/)
- Companion docs: [architecture-overview.md](../architecture-overview.md),
  [user-manual.md](../user-manual.md), [installation-manual.md](../installation-manual.md)
- User-testing reports: [user-testing-papi-vision-2026-05-28.md](../user-testing-papi-vision-2026-05-28.md),
  [user-testing-papi-vision-rerun-2026-05-28.md](../user-testing-papi-vision-rerun-2026-05-28.md)
- Audit: [audit-fix-verification-2026-05-28.md](../audit-fix-verification-2026-05-28.md)

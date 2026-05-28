# Interim Presentation — Content Outline

> Slide-by-slide content for the **Wed 2026-06-03 08:30** interim
> presentation (20 % of the module grade). The team styles this
> into the actual deck (PowerPoint / Keynote / Google Slides) using
> the design tokens in `01-design-document.md §4`.
>
> Speaker assignments are placeholders — adjust before rehearsal.
> Total target: **15 minutes content + 5 minutes Q&A**.

## Speaker plan

Rotate ownership so every member speaks (LR3 13-15 marker "each
member speaks during the presentation"). Four speakers, ~3.5 min
each. Cue cards are in §"Per-slide content" below.

| Member | Section | Slides |
|---|---|---|
| **Rooms Maxim** | Open + product context | 1, 2, 3 |
| **Sousa Rodrigo** | Data + model story | 4, 5, 6 |
| **Chekhun Maksym** | Engineering + live demo | 7, 8, 9 |
| **Kattan Hamzzah** | Project mgmt + next steps + close | 10, 11, 12, 13 |

## Per-slide content

### Slide 1 — Title

```
PAPI Vision
AI-assisted approach-light verification

Howest Industry Project · Sprint review #1
Bachelor CTAI · 2025-2026

Sousa Rodrigo · Chekhun Maksym · Kattan Hamzzah · Rooms Maxim
Client: Intersoft Electronics Services BV (Daoud Uahabi)
Wednesday 2026-06-03
```

Talking point (15 s): "We're three weeks in. Here's where we are
and where we're going."

### Slide 2 — The problem in 30 seconds

Visual: photo of a PAPI installation at dusk, four lamps, two red
two white, glidepath line overlay.

Bullets:

- PAPI = Precision Approach Path Indicator. Four lights at the
  threshold of a runway. Pilots read white/red counts to stay on
  the 3° glidepath.
- Today: checked by an engineer with a theodolite — every airport,
  every periodic recommissioning.
- Intersoft wants this verified from drone footage — faster,
  documented, repeatable.

Talking point (30 s): set the stakes. Don't mention the model yet.

### Slide 3 — What we built

Screenshot: Live Demo page with a real result, "Correct glidepath"
on screen, all four lamp cards visible.

Bullets:

- A web application that ingests a drone image, video, or folder.
- Detects each of the four lamps with a custom-trained YOLO model.
- Computes per-lamp state — *white / red / transition* — by
  combining detection with airport geometry.
- Reports the global glidepath state (one of five) and a
  per-lamp confidence + transition meter.

Talking point (45 s): walk through the screenshot left to right —
input, evidence, output.

### Slide 4 — The dataset

Visual: 2×2 grid — day rwy24 wide, night rwy06 wide, day rwy24
zoom, day rwy24 transition close-up.

Numbers (verbatim from BigBrain hub):

- **4 058 frames** from a single DJI Matrice 4E drone, single
  airport (Friedrichshafen, EDNY).
- **5 night flights** targeting rwy 06 (626 frames).
- **16 day flights** targeting rwy 24 (3 432 frames).
- Two regimes (day / night), two runways (06 / 24), two cameras
  (Wide / Zoom).

Talking point (45 s): "Single airport — by design. Generalisation
to other airports is out of scope for v1.0; what we *do* claim is
generalisation across the four orthogonal axes — runway, time of
day, distance, camera."

### Slide 5 — Why we chose two detection classes, not three

Visual: side-by-side — left, the naïve approach (3 YOLO classes:
red / white / transition); right, our approach (2 YOLO classes +
geometric promotion).

Bullets:

- **Naïve**: ask the model to learn three classes including
  *transition*. Problem: transition is rare, geometrically defined,
  and the label boundaries depend on the *angular* position which a
  per-frame image classifier cannot see.
- **Ours**: model predicts only `red` / `white`. At response time
  the backend computes the camera-to-lamp elevation angle from
  drone GPS + surveyed lamp coords, and promotes the state to
  `transition` when `|elevation − set_angle| ≤ 0.10°`.
- One source of truth lives in `packages/papi/src/papi/lamp_state.py`,
  reused by both the online inference path and the offline
  auto-labelling pipeline.

Talking point (60 s): this is the engineering insight — frame this
as the team's main design decision, not as a YOLO tutorial.

### Slide 6 — Model performance (interim snapshot)

Visual: confusion matrix from the latest eval run +
per-class precision/recall + F1.

Bullets:

- Detector: YOLO 26n, fine-tuned on EDNY frames.
- Hold-out test split: **<!-- TEAM: latest test-split F1, precision, recall numbers
  from workflows/notebooks/04_yolov26n_sequence_model_evaluation.ipynb -->**
- Per-state F1: red **<!-- TEAM: red F1 -->**, white **<!-- TEAM: white F1 -->**.
- Transition recall on the verification sample (1 092 day +
  36 night frames): **<!-- TEAM: transition recall -->**.

Talking point (45 s): "Numbers are interim. Final-presentation
slide will show the same chart against a YOLO-26s and YOLO-26m
baseline so the band-lift comparison is on the record."

### Slide 7 — System architecture (one diagram)

Visual: the block diagram from `04-components-overview-a4.md` —
offline pipeline on the left, online stack on the right.

Bullets:

- Five Docker services: Postgres, FastAPI backend, Nginx + React
  frontend.
- Three containers run as non-root; secrets via `.env`; healthchecks
  on every service.
- CI runs ruff + 43 backend tests + 15 papi tests + npm lint/build
  + Docker build on every push.

Talking point (60 s): no surprises here — keep it short, this slide
exists so the jury knows the engineering is intentional.

### Slide 8 — Live demo (3 minutes)

**No bullets — the screen is the demo.**

Demo flow (rehearsed timing):

1. Open `http://localhost:5173/`. **(10 s)**
2. Click "Try it out" → Live Demo. **(5 s)**
3. Drag a folder from `test_videos/_folder_test/` onto the upload
   zone. **(10 s)**
4. Pick PAPI 24 from the runway dropdown. **(5 s)**
5. Click *Run backend model*. While it processes, narrate the
   per-lamp state cards and the transition meter. **(60 s)**
6. Step through frames with `←` / `→` arrows. Show one TRANSITION
   frame. **(30 s)**
7. Switch to Insights. Show the state-decoder bar + the transition
   ribbon. Click *Download charts (PDF)*. **(40 s)**

Fallback if the demo fails: pre-recorded MP4 of the same flow
checked into `docs/deliverables/assets/demo-fallback.mp4` (todo:
record this Mon evening so we have it ready Wed morning).

### Slide 9 — Engineering practices we want graders to notice

Three columns — each a stat with a one-sentence explanation.

```
┌───────────────────┬───────────────────┬──────────────────┐
│  CI on every push  │  43 + 15 tests    │ Audit-tracked    │
│                   │                   │                  │
│ ruff + pytest +   │ Backend +         │ Every fix tagged │
│ npm lint/build +  │ papi-package      │ B-CRIT, B-MAJ,   │
│ Docker build      │ unit tests        │ F-CRIT, etc.     │
│                   │                   │                  │
│ 100 % green on    │ Run by CI on      │ 39 issues        │
│ main since        │ every push        │ tracked,         │
│ 2026-05-26        │                   │ 36 closed        │
└───────────────────┴───────────────────┴──────────────────┘
```

Talking point (45 s): "These three things are how we kept the
codebase from collapsing under sprint pressure."

### Slide 10 — Project management evidence

Visual: a screenshot of the Trello board + a small burndown chart.

Bullets:

- **Trello** sprint board, four members, daily standup. Link:
  <https://trello.com/b/iLrmBsgI/papi-industry-project-sprints>.
- **Burndown** (right): **<!-- TEAM: burndown chart for sprints 1-3 -->**.
- **Retro** highlights (sprint 2): **<!-- TEAM: 2-3 bullets -->**.
- **Time tracking**: **<!-- TEAM: total hours per member, sprint 1-3 -->**.
- **Client meetings** held: kickoff (18/05), dataset confirmation
  (19/05), geometry (26/05). Reports in submission packet.

Talking point (60 s): tie the management evidence back to the
*choices* — e.g. "the retro after sprint 2 is why we pivoted to
geometry-driven labelling."

### Slide 11 — Where we are vs the plan

Three columns:

```
┌────────────────────┬────────────────────┬────────────────────┐
│ Sprint 1 (done)    │ Sprint 2 (done)    │ Sprint 3 (in flight)│
│                    │                    │                    │
│ Data pipeline      │ Backend API        │ Edge benchmark     │
│ Calibration        │ Frontend SPA       │ Model comparison   │
│ Auto-label v1      │ Docker stack       │ A11y polish        │
│ CVAT verify        │ CI green           │ Final deliverables │
│                    │ User testing × 2   │                    │
└────────────────────┴────────────────────┴────────────────────┘
```

Talking point (45 s): "Sprint 1 and 2 closed on time. Sprint 3 is
under way. Here's the velocity — three sprints, no slippage."

### Slide 12 — What's next (last 2 sprints)

Bullets (taken from the plan-file remediation list):

- **Closing**: edge-benchmark on real hardware (Pi 5 + Jetson Orin
  Nano), cost projection, alternative-model comparison (26s vs 26n).
- **Confirming**: PAPI 06 height + 461.37 datum from Daoud
  (Mon 2026-06-01 client meeting).
- **Polishing**: design document, A3 promotional poster, frontend
  test suite, accessibility form-control IDs.
- **Submitting** Fri 2026-06-19: final presentation, user manual,
  install manual, source zip, technical-components A4, A3 poster,
  weekly reports bundle.

Talking point (45 s): be honest about the open items — graders
reward "we know what's left" over "we're done already."

### Slide 13 — Close + Q&A

```
PAPI Vision — Interim review

✔  Real-time-capable PAPI detection + classification
✔  Geometry-driven transition state (one source of truth)
✔  Dual-runway, dual-camera, dual-regime dataset
✔  Hardened Docker stack with CI + automated tests
✔  Two user-testing rounds with documented iteration

Source code · https://github.com/MaximRoomsHowest/PAPI-Detection-and-Classification
Scrum board · https://trello.com/b/iLrmBsgI/papi-industry-project-sprints
Contact · {rodrigo|maksym|hamzzah|maxim}@student.howest.be

Thank you. Questions?
```

Talking point (30 s): leave time for ≥ 5 minutes of Q&A. Pre-brief
each speaker on the *one* question they're the canonical expert on.

## Demo rehearsal checklist (Tue 2026-06-02 evening)

- [ ] `docker compose up -d --build` cold-start from a fresh `.env`
- [ ] Open `http://localhost:5173/` in Chrome, Firefox, Safari
- [ ] Run the §8 demo flow end-to-end, time each step
- [ ] Re-run the user-testing-rerun verification commands:
  ```powershell
  .venv\Scripts\python.exe -m pytest packages/papi/tests
  cd apps\backend; ..\..\.venv\Scripts\python.exe -m pytest
  cd ..\frontend; npm run lint; npm run build
  ```
- [ ] Screenshot the green output and tape it into the speaker
  notes so the team can flash it if the live demo glitches.
- [ ] Record the fallback MP4 (see Slide 8).
- [ ] Confirm GitHub Actions on `main` shows green badge.

## Submission packet (Wed 2026-06-03 by 08:30)

Four PDFs uploaded separately on Leho:

1. This deck → PDF.
2. `05-project-management-summary.md` → PDF.
3. `meeting-reports/2026-05-18-kickoff.md`,
   `meeting-reports/2026-05-19-dataset-confirmation.md`,
   `meeting-reports/2026-05-26-geometry.md` → 3 separate PDFs (or
   bundled into one — Leho accepts both).
4. *Not applicable for CTAI* — MCT-only functional analysis.

## Pre-Q&A briefings — who answers what

To avoid the rubric LR3 *insufficient* marker "can't smoothly answer
jury questions":

| Likely question | Canonical speaker | Prep notes |
|---|---|---|
| Why two YOLO classes? | Sousa Rodrigo | §5 of design doc |
| Edge deployment / FPS / cost? | Chekhun Maksym | `edge-benchmark.md` |
| How did you handle dual runways? | Rooms Maxim | `papi-detection-and-classification` README + `papi_edny.yaml` |
| How are sprints organised? | Kattan Hamzzah | Trello board + retros |
| Security, auth, deploy? | Chekhun Maksym | `architecture-overview.md §7` |
| Generalisation to other airports? | Sousa Rodrigo | Out-of-scope; one config per airport |
| What's not done yet? | Kattan Hamzzah | Slide 12 list verbatim |

Rehearse each answer in **≤ 30 seconds**; jurors penalise rambling.

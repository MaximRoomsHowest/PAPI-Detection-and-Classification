# Final Presentation — Content Outline

> Slide-by-slide content for the **Fri 2026-06-19 08:30** final
> presentation (60 % of the module grade — combined with project
> quality assessment). The team styles this into the actual deck
> using the design tokens in `01-design-document.md §4`.
>
> Total target: **20 minutes content + 10 minutes Q&A**. Longer
> than the interim because the jury weighs depth and the handover
> narrative.

## What's different from the interim

This deck is a **delivery presentation**, not a progress update:

- Replace "what we plan" language with "what we shipped".
- Add real edge-benchmark numbers (the §5 [TODO] cells will be
  filled by sprint 4 / 5).
- Add the alternative-model comparison (yolo26n vs 26s vs 26m) —
  band-lift evidence for LR1D 16+.
- Add a proof-of-handover slide (see §"Slide 14" below).
- Add a "what we learned" reflection (LR3 16+ "every member can
  enthuse the jury").
- Drop the "what's next in sprint 3" slide entirely.

## Speaker plan

Same rotation as the interim so the team practiced the same hand-offs,
but adjusted for the final's longer runtime. Five sections × ~4 min.

| Member | Section | Slides |
|---|---|---|
| **Rooms Maxim** | Open + the problem (what + why) | 1, 2, 3 |
| **Sousa Rodrigo** | Data + model + comparison | 4, 5, 6, 7 |
| **Chekhun Maksym** | Engineering + edge benchmark + live demo | 8, 9, 10, 11 |
| **Kattan Hamzzah** | Project mgmt + retro + reflection | 12, 13 |
| **All four** | Handover + close + Q&A | 14, 15 |

## Per-slide content

### Slide 1 — Title

```
PAPI Vision
Safer landings, seen from the sky.

Final delivery · Industry Project 2026
Howest CTAI · Bachelor

Sousa Rodrigo · Chekhun Maksym · Kattan Hamzzah · Rooms Maxim
Client: Intersoft Electronics Services BV (Daoud Uahabi)
Friday 2026-06-19
```

Talking point (15 s): "We're delivering. Five sprints, one product."

### Slide 2 — The problem we solved

Visual: a single PAPI installation photo at dusk.

Bullets:

- PAPI = Precision Approach Path Indicator. Pilots read 4-light
  white/red patterns to stay on the 3° glidepath.
- Current verification: an engineer with a theodolite, every
  airport, every periodic recommissioning. Slow, manual,
  documentation-poor.
- We built drone-based verification — captured imagery, automated
  detection + classification, documented and replayable.

Talking point (30 s): set stakes again; assume some jurors didn't
see the interim.

### Slide 3 — What we delivered (one image)

Screenshot: a real result page with "Correct glidepath", all four
lamps, transition meter, confidence numbers.

Three bullets, no more:

- A web application that ingests drone images / videos / folders.
- A trained detection + classification model for two-light states.
- Reproducible from `docker compose up -d --build` in under five minutes.

Talking point (30 s): the headline. The next 18 minutes back this
up with evidence.

### Slide 4 — The dataset (final form)

Visual: 2 × 2 grid + final counts.

Numbers:

- **4 058 frames**, single airport (Friedrichshafen EDNY).
- 5 night flights → rwy 06 (626 frames).
- 16 day flights → rwy 24 (3 432 frames).
- Two cameras (Wide / Zoom).
- **Train / val / test** split is flight-level, regime-aware (see
  `configs/split.yaml`). The test set spans 3 regimes: 1000 m day
  wide, 300 m day zoom, 500 m night wide.

Talking point (40 s): defend the *split*, not the size. Random
frame splits would leak; the held-out flight design is what makes
the eval honest.

### Slide 5 — How we labelled it without 4 000 manual frames

Visual: side-by-side — left, naïve "label every frame in CVAT"; right,
our geometry-driven projection pipeline.

Bullets:

- Manual labelling of 4 058 frames was infeasible.
- We **project surveyed lamp coordinates** through the calibrated
  DJI gimbal Euler convention into image pixels — a bounding box
  per lamp, per frame, for free.
- We **manually corrected** 2 984 boundary-case frames in CVAT
  (~73 % of the set) — those with RTK uncertainty, zoom-camera, or
  near a transition.
- Calibration achieves median 6.05 px residual, max 21.0 px across
  48 LRF bore-sight frames × 16 flights.

Talking point (60 s): this is the engineering insight worth
emphasising — frame it as "we made labelling tractable", not "we
auto-labelled".

### Slide 6 — Two classes, transition inferred geometrically

Visual: a tracked sequence — three frames in a row showing a single
lamp transitioning from white through transition to red, with the
elevation-angle reading below each frame.

Bullets:

- YOLO model has **two** classes: `papi_light_red` (0) and
  `papi_light_white` (1).
- *Transition* is **computed**, not learned — at response time the
  backend computes the elevation angle from drone GPS + surveyed
  lamp coords, and promotes the state when
  `|elevation − set_angle| ≤ 0.10°`.
- One source of truth: `packages/papi/src/papi/lamp_state.py`,
  shared by both the online inference path and the offline
  auto-labelling pipeline.

Talking point (60 s): "Transition is rare and ill-defined as a
visual class. Geometry has it exactly. So we let geometry decide."

### Slide 7 — Model results vs alternatives

Visual: bar chart comparing **yolo26n / 26s / 26m** on the
held-out test split.

| Model | Params | Detection F1 | Per-state F1 | p50 latency (laptop CPU) | fps@p50 (Jetson INT8) |
|---|---:|---:|---:|---:|---:|
| yolo26n (current) | 2.6 M | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** |
| yolo26s | 9.1 M | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** |
| yolo26m | 24 M | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** |

Bullets:

- We trained all three on the same split.
- The chosen variant is **<!-- TEAM: yolo26n based on real-time fps
  requirement, OR yolo26s if accuracy delta justifies the cost
  -->**.
- See `docs/deliverables/06-model-comparison.md` for the full
  methodology and trade-off table.

Talking point (60 s): hits the LR1D 16+ "alternative AI models
implemented when they add value" marker directly.

### Slide 8 — System architecture (deployed view)

Visual: the `04-components-overview-a4.md` block diagram.

Bullets:

- Five services in Docker compose: Postgres, FastAPI backend,
  Nginx + React frontend.
- Three containers run as non-root, secrets via `.env`, healthchecks
  on every service, end-to-end `X-Request-ID` tracing.
- CI runs ruff + 43 backend tests + 15 papi tests + 6 frontend
  tests + npm lint/build + Docker build on every push.
- HTTPS termination via Caddy in production (one-line `docker
  compose` swap — see `docs/installation-manual.md §Production`).

Talking point (60 s): keep short; the diagram does the work.

### Slide 9 — Edge deployment — how it actually performs

Visual: bar chart of latency from `docs/edge-benchmark.md §5` filled
in.

| Device | Model | p50 ms | fps@p50 | RSS MB |
|---|---|---:|---:|---:|
| Laptop CPU | best.pt (FP32) | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** |
| Raspberry Pi 5 | best_int8.onnx | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** |
| Jetson Orin Nano (INT8) | best_int8.onnx | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** |
| Intel NUC i7 | best.pt | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** |

Bullets:

- Real-time target was **≥ 10 fps**.
- Recommended deployment: **<!-- TEAM: per §8 of edge-benchmark.md -->**.
- INT8 quantisation cost: **<!-- TEAM: ΔF1 between best.pt and best_int8.onnx -->**.
- Three-year TCO per airport: **<!-- TEAM: per §7.4 of edge-benchmark.md -->**.

Talking point (90 s): this is the LR1B + LR1D 16+ evidence — real
numbers, honest fall-backs, named recommendation.

### Slide 10 — Live demo (4 minutes)

Same flow as the interim, expanded:

1. Open Live Demo, single-image upload with GPS metadata.
2. Show per-lamp confidence + transition meter + elevation angles.
3. Switch to a folder upload and step through frames including a
   transition frame.
4. Open Insights, show the state-decoder + transition ribbon.
5. Click **Download charts (PDF)** to demonstrate the artifact.
6. Open History, click a past run, show the same detail panel.

Fallback: pre-recorded MP4 at `docs/deliverables/assets/demo-fallback.mp4`.

### Slide 11 — Engineering practices we want graders to notice

Same three-column layout as the interim slide 9, updated:

```
┌───────────────────┬───────────────────┬───────────────────┐
│ CI green every    │ 43 + 15 + 6 tests │ 39 audit issues   │
│ push since        │ across backend,   │ tracked,          │
│ 2026-05-26        │ papi, frontend    │ 36 closed         │
│                   │                   │                   │
│ ruff + pytest +   │ Geometry math has │ Every fix tagged  │
│ npm test +        │ dedicated unit    │ in commit msgs    │
│ Docker build      │ tests now (+12)   │ for traceability  │
└───────────────────┴───────────────────┴───────────────────┘
```

Talking point (45 s): tie practices back to outcomes — "the audit
backlog closed in two sprints because the tags survived in commits."

### Slide 12 — How we ran the project

Visual: stacked-area burndown across all five sprints + a Trello
screenshot.

Bullets:

- Trello board, four members, daily 09:30 standup on Discord.
- 5 one-week sprints, retro after each (Glad / Sad / Mad / Add).
- 4 client meetings on record (kickoff, two syncs, closure).
- Weekly P2P evaluations submitted on Leho.
- Time tracking: **<!-- TEAM: total team hours, range per member -->**.

Talking point (60 s): pure LR2 + LR3 evidence. Keep tone modest.

### Slide 13 — What we learned

A reflection slide. Five bullets — one per member + one team.

- **Rodrigo**: **<!-- TEAM: e.g. "Geometric labelling at scale
  changed how I think about supervised data — projecting
  surveyed coords saved 70 % of manual annotation hours." -->**.
- **Maksym**: **<!-- TEAM -->**.
- **Hamzzah**: **<!-- TEAM -->**.
- **Maxim**: **<!-- TEAM -->**.
- **Team**: **<!-- TEAM: e.g. "Same-day user-testing iteration was
  the highest-leverage process change in the whole project — round
  1 caught six demo blockers, round 2 verified the fixes by lunch." -->**.

Talking point (60 s): this is LR3 16+ "every member can enthuse the
jury". Practise this slide more than any other.

### Slide 14 — Handover to the client

Visual: a screenshot of the handover email + the receipt confirmation.

Bullets:

- **Handed over Tue 2026-06-17** to Daoud Uahabi (Intersoft
  Electronics Services BV).
- Materials: source ZIP, user manual, installation manual, edge
  benchmark report, model registry, and a Slack-style support
  channel pinned for the first 30 days.
- See `docs/deliverables/10-client-handover-email.md` for the
  artifact.

Talking point (45 s): satisfies the Leho "proof of handover to the
client" requirement; doubles as a closing punctuation mark.

### Slide 15 — Close + Q&A

```
PAPI Vision — Delivered

✔  Drone → web app → traceable verdict in ~ 2 s per frame
✔  Two-class detector + geometric transition (one source of truth)
✔  Dual runway, dual camera, dual regime — flight-level eval
✔  Real-time on Jetson Orin Nano (INT8)
✔  Three-year TCO ≈ <!-- TEAM --> EUR per airport
✔  Hardened Docker stack with CI + tests + audit-tracked issues
✔  Two user-testing rounds with same-day iteration
✔  Handed over to Intersoft, with support window

Source · https://github.com/MaximRoomsHowest/PAPI-Detection-and-Classification
Contact · {rodrigo|maksym|hamzzah|maxim}@student.howest.be

Thank you. Questions?
```

Talking point (30 s): leave ≥ 10 minutes for Q&A; pre-brief each
speaker on their canonical question (see §"Pre-Q&A briefings" below).

## Demo rehearsal checklist (Thu 2026-06-18 evening)

Same as the interim plus the additional final-day items:

- [ ] Full CI green on `main` at the commit being submitted
- [ ] `docker compose up -d --build` cold-start verified on a fresh
      Windows + macOS + Linux laptop (rotate one each per team
      member)
- [ ] Live demo runs in Chrome, Firefox, Safari without warning
- [ ] Re-run user-testing-rerun verification commands; tape the
      green screenshot into speaker notes
- [ ] Fallback MP4 recorded the evening before (≤ 24 h old)
- [ ] Source ZIP generated via `git archive --format=zip
      --output=papi-vision-source-{commit}.zip HEAD`
- [ ] Every `<!-- TEAM: ... -->` marker in `docs/deliverables/*.md`
      filled (`Select-String -Path docs\deliverables -Pattern
      "TEAM:" -Recurse`)
- [ ] PDFs in `docs/deliverables/*.pdf` regenerated via
      `scripts/build-deliverables.ps1`
- [ ] All Leho upload slots populated (cross-check
      `docs/deliverables/README.md §Final`)
- [ ] Coaches (Dieter, Martijn, Gilles, Nathan, Frederik) confirmed
      access to repo + Trello

## Pre-Q&A briefings — who answers what (updated for final)

| Likely question | Canonical speaker | Prep notes |
|---|---|---|
| Why two YOLO classes, not three? | Sousa Rodrigo | §6 of this outline + design doc §11 |
| Edge fps, cost, recommendation? | Chekhun Maksym | `edge-benchmark.md` §5/§7/§8 |
| How did model comparison play out? | Sousa Rodrigo | `06-model-comparison.md` |
| Domain adaptation / new airport? | Rooms Maxim | One YAML per airport; `configs/papi_edny.yaml` is the template |
| Security / auth / production deployment? | Chekhun Maksym | `architecture-overview.md §7` + install manual `Production` section |
| Sprint mgmt, P2P, time | Kattan Hamzzah | `05-project-management-summary.md` |
| What's not done yet / known limits? | Rooms Maxim | `architecture-overview.md §8` |
| Handover, support window? | Sousa Rodrigo | `10-client-handover-email.md` |
| How honest are the visuals? | Any (this is a values question) | Design doc §1 "Honest visuals" principle |

Each answer rehearsed in **≤ 30 seconds**.

## Submission packet (Fri 2026-06-19 by 08:30)

Each as a separate Leho upload (PDF / ZIP / MP4 as the slot
allows). Cross-reference `docs/deliverables/README.md §Final`:

1. This deck → PDF.
2. Weekly meeting reports bundle (≥ 5 reports → one PDF or zipped).
3. `user-manual.md` → PDF.
4. `installation-manual.md` → PDF.
5. `05-project-management-summary.md` → PDF (final version).
6. `papi-vision-poster-A3.pdf` (per `08-promotional-poster-brief.md`).
7. Source-code ZIP via `git archive`.
8. `04-components-overview-a4.md` → PDF (1 A4 page).
9. *Not applicable for CTAI*.
10. Additional rubric-implied: `01-design-document.md` → PDF.

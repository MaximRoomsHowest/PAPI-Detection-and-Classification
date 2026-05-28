---
title: "PAPI Vision — Project Management Summary"
subtitle: "Sprint backlogs · burndown · retrospectives · time tracking"
date: "2026-06-03 (interim) · 2026-06-19 (final)"
mainfont: "Calibri"
fontsize: 10pt
geometry: "a4paper, margin=2cm"
---

# Project Management Summary

> **Rubric**: required artifact for **LR2** ("PDF with global project
> overview — WBS, time …") and evidence for the **LR2 16+** band
> markers *issue-tracking integration* and *continuous integration*.
>
> This is a template: fill in the `<!-- TEAM: ... -->` markers with
> data from Trello + git + the team's own time logs before each PDF
> export. List the fill-in points in one pass:
> `Select-String -Path 05-project-management-summary.md -Pattern "TEAM:"`

## 1. Project at a glance

- **Title** — PAPI Vision: AI-assisted approach-light verification
- **Client** — Intersoft Electronics Services BV (Daoud Uahabi)
- **Course** — Howest Industry Project, CTAI, 2025-2026
- **Team** — Sousa Rodrigo · Chekhun Maksym · Kattan Hamzzah · Rooms Maxim
- **Duration** — 18 May → 19 June 2026 (5 weeks)
- **Repository** — <https://github.com/MaximRoomsHowest/PAPI-Detection-and-Classification>
- **Scrum board** — <https://trello.com/b/iLrmBsgI/papi-industry-project-sprints>
- **CI** — GitHub Actions (`.github/workflows/ci.yml`), green on `main`
- **Issue tracking** — Trello cards + BigBrain `papi-improvements-audit-2026-05-27`

## 2. Work Breakdown Structure (WBS)

Three top-level work packages mirror the three deliverable layers:
**Data + Model**, **Application**, **Project ceremony**.

```
PAPI Vision
├── 1. Data + Model
│   ├── 1.1 Dataset preparation
│   │   ├── 1.1.1 Raw drone capture ingest (Intersoft → team)
│   │   ├── 1.1.2 Per-frame metadata extraction (EXIF + DJI XMP)
│   │   ├── 1.1.3 Calibration: DJI gimbal Euler convention
│   │   └── 1.1.4 Sequence-tracking dataset (day / night × wide / zoom)
│   ├── 1.2 Auto-labelling
│   │   ├── 1.2.1 Geometry-driven label projection
│   │   ├── 1.2.2 CVAT verification sample (2 984 frames)
│   │   └── 1.2.3 Two-class label spec (red / white)
│   ├── 1.3 Model training
│   │   ├── 1.3.1 YOLO 26n baseline
│   │   ├── 1.3.2 Hyperparameter tuning
│   │   ├── 1.3.3 Sequence model evaluation
│   │   └── 1.3.4 INT8 ONNX export
│   └── 1.4 Edge benchmark
│       ├── 1.4.1 Local Windows CPU smoke test (DONE)
│       ├── 1.4.2 Raspberry Pi 5 measurements
│       ├── 1.4.3 Jetson Orin Nano measurements
│       └── 1.4.4 Cost-per-airport projection
├── 2. Application
│   ├── 2.1 Backend (FastAPI)
│   │   ├── 2.1.1 Inference service + ByteTrack tracking
│   │   ├── 2.1.2 Analysis-log repository (Postgres)
│   │   ├── 2.1.3 Pydantic v2 schemas
│   │   └── 2.1.4 Authentication (X-API-Key) + structured logging
│   ├── 2.2 Frontend (React 19 + Vite 8)
│   │   ├── 2.2.1 Live Demo page (single / video / folder upload)
│   │   ├── 2.2.2 Insights page (state decoder + transition ribbon)
│   │   ├── 2.2.3 History page (paginated audit trail)
│   │   ├── 2.2.4 Multi-language (en/nl/fr) + dark theme
│   │   └── 2.2.5 PDF export (Insights → jsPDF)
│   ├── 2.3 Infrastructure
│   │   ├── 2.3.1 Docker compose (Postgres + backend + frontend)
│   │   ├── 2.3.2 Nginx reverse proxy (non-root, security headers)
│   │   └── 2.3.3 GitHub Actions CI
│   └── 2.4 Verification
│       ├── 2.4.1 43 backend tests + 15 papi tests on CI
│       ├── 2.4.2 Frontend lint + build on CI
│       └── 2.4.3 User testing × 2 rounds (2026-05-28)
└── 3. Project ceremony
    ├── 3.1 Sprint mechanics
    │   ├── 3.1.1 Five one-week sprints
    │   ├── 3.1.2 Daily standup (Discord)
    │   └── 3.1.3 End-of-sprint retro
    ├── 3.2 Client engagement
    │   ├── 3.2.1 Weekly client meeting
    │   ├── 3.2.2 Meeting report per session
    │   └── 3.2.3 Open-questions log (BigBrain)
    └── 3.3 Deliverables
        ├── 3.3.1 Interim presentation (03/06)
        ├── 3.3.2 User manual + install manual
        ├── 3.3.3 Architecture overview + design document
        ├── 3.3.4 Promotional A3 poster + components A4 overview
        └── 3.3.5 Final presentation + source ZIP (19/06)
```

## 3. Sprint backlogs

### 3.1 Sprint 1 — Data + calibration (18 → 22 May)

| Card | Owner | Effort (pts) | Status | Notes |
|---|---|---|---|---|
| Dataset import + EXIF/XMP metadata extraction | Rodrigo | 5 | done | `packages/papi/metadata.py` |
| Calibrate DJI gimbal Euler convention | Rodrigo | 8 | done | Median 6.05 px residual on 48 frames |
| Two-class label spec (red / white) | Maxim | 3 | done | `docs/label_spec.md` |
| Geometry-driven auto-labelling | Hamzzah | 8 | done | `packages/papi/projection.py` |
| CVAT export pipeline | Maksym | 5 | done | `workflows/scripts/export_yolo_assisted_cvat.py` |
| Sequence-tracking dataset | Maxim | 5 | done | `data/datasets/papi_lamp_sequences/` |
| **Sprint 1 total** | | **34 pts** | **34 / 34 done** | |

**<!-- TEAM: confirm card titles match Trello; adjust owner + points to match actual sprint board. Add any cards I missed. -->**

### 3.2 Sprint 2 — Backend + frontend MVP (25 → 29 May)

| Card | Owner | Effort (pts) | Status | Notes |
|---|---|---|---|---|
| FastAPI scaffold + inference service | Maksym | 8 | done | `apps/backend/app/services/inference.py` |
| Pydantic v2 schemas + validation | Maksym | 3 | done | `apps/backend/app/validation/schemas.py` |
| Postgres + analysis-log repository | Rodrigo | 5 | done | `apps/backend/app/repositories/` |
| React Live Demo page (single + folder) | Hamzzah | 8 | done | `apps/frontend/src/App.jsx` |
| Insights page + PDF export | Maxim | 5 | done | Plotly + jsPDF |
| Docker compose hardening | Maksym | 5 | done | Non-root, secrets via `.env`, healthchecks |
| User testing round 1 + audit fixes | All | 8 | done | `docs/user-testing-*-2026-05-28.md` |
| GitHub Actions CI | Rodrigo | 3 | done | `.github/workflows/ci.yml` |
| **Sprint 2 total** | | **45 pts** | **45 / 45 done** | |

**<!-- TEAM: as above, reconcile with Trello. -->**

### 3.3 Sprint 3 — Edge + polish (1 → 5 June, in flight)

| Card | Owner | Effort (pts) | Status | Notes |
|---|---|---|---|---|
| Client meeting #3 — close PAPI 06 geometry | Rodrigo | 2 | doing | Mon 2026-06-01 14:30 |
| Edge benchmark on Raspberry Pi 5 | Maksym | 5 | todo | `workflows/scripts/edge_benchmark.py` |
| Edge benchmark on Jetson Orin Nano | Maksym | 5 | todo | Same |
| Alternative-model comparison (26s vs 26n) | Rodrigo | 5 | todo | `workflows/notebooks/04_*` |
| Design document | Hamzzah | 3 | doing | `docs/deliverables/01-design-document.md` |
| Cost-per-airport projection | Maxim | 3 | todo | `docs/edge-benchmark.md §7` |
| Frontend Vitest setup + smoke tests | Hamzzah | 5 | todo | `apps/frontend/` |
| A11y form-control IDs | Maxim | 1 | todo | Audit USERTEST-MINOR-1 |
| Interim deck + rehearsal | All | 5 | doing | Wed 03/06 |
| **Sprint 3 planned** | | **34 pts** | | |

### 3.4 Sprint 4 — Final polish (8 → 12 June, planned)

| Card | Owner | Effort (pts) | Status | Notes |
|---|---|---|---|---|
| Promotional A3 poster | Maxim | 5 | todo | `docs/deliverables/08-promotional-poster-brief.md` |
| 1-page A4 components overview | Hamzzah | 1 | done | `docs/deliverables/04-components-overview-a4.md` |
| Model registry / lineage doc | Rodrigo | 2 | todo | `models/MODELS.md` |
| Interpretability surface (confidence heatmap) | Hamzzah | 5 | todo | LR1D band-lift |
| Production-mode rejection of default DB creds | Maksym | 2 | todo | Audit risk #2 |
| Close `/media` auth gap | Maksym | 3 | todo | Audit risk #1 |
| HTTPS/TLS paragraph in install manual | Rodrigo | 1 | todo | LR1C band-lift |
| Final presentation rehearsal | All | 5 | todo | Wed 17/06 evening |
| **Sprint 4 planned** | | **24 pts** | | |

### 3.5 Sprint 5 — Submission (15 → 19 June, planned)

| Card | Owner | Effort (pts) | Status | Notes |
|---|---|---|---|---|
| Convert user-manual.md to PDF | Hamzzah | 1 | todo | Pandoc |
| Convert installation-manual.md to PDF | Hamzzah | 1 | todo | Pandoc |
| Render every `docs/deliverables/*.md` to PDF | Maksym | 1 | todo | Pandoc loop |
| Source-code ZIP via `git archive` | Maksym | 1 | todo | Submission day |
| Final presentation Friday 19/06 | All | 5 | todo | Live |
| Proof-of-handover email to Daoud | Rodrigo | 1 | todo | Tue 17/06 |
| **Sprint 5 planned** | | **10 pts** | | |

## 4. Burndown chart

**<!-- TEAM: insert the burndown chart for sprints 1-3 here. Generate
from Trello using one of:
  - Trello + Burnup-style power-up
  - Manual export → Excel chart
  - Python script: `workflows/scripts/burndown.py <BOARD_ID>` (write
    this as a small script if helpful).
A simple stacked-area chart of done / doing / todo points per day
across sprints 1 → 3 is sufficient. -->**

Caption: "Burndown sprints 1-3. Ideal line (dashed) vs actual
(solid). Sprint 1 closed on time; sprint 2 closed on time with one
card slipping into sprint 3 (the user-testing rerun); sprint 3 in
flight as of 2026-05-28."

## 5. Sprint retrospectives

Format: **Glad / Sad / Mad / Add** — short, actionable, max five
items per quadrant.

### 5.1 Sprint 1 retro (held 2026-05-22)

| Glad | Sad | Mad | Add (next sprint) |
|---|---|---|---|
| Calibration converged on first try (median 6.05 px) | Auto-label took longer than estimated — geometry boundary cases harder than expected | Dataset confirmation arrived on Mon, not Fri — blocked sprint 1 planning | Push the client for sprint-start blockers on Fri the week before |
| Two-class label spec landed early | ZoomCamera focal-length absent from XMP — sprint 2 risk | | Add a "blockers from client" column to Trello |
| **<!-- TEAM: add a glad point -->** | **<!-- TEAM: add a sad point -->** | | **<!-- TEAM: add an Add -->** |

### 5.2 Sprint 2 retro (held 2026-05-29)

| Glad | Sad | Mad | Add |
|---|---|---|---|
| Backend + frontend wired in 2 days | User-testing round 1 surfaced 6 demo blockers — same day fix sprint felt rushed | Plotly CJS→ESM regression cost a full afternoon | Schedule user-testing earlier in the sprint, not the last morning |
| Docker stack hardened (non-root, secrets, healthchecks) | App.jsx grew to 2 469 lines — modularisation deferred | | Add modularisation card to sprint 4 backlog |
| Two user-testing rounds done in one day with iteration | | | |
| CI green by Wed | | | |
| **<!-- TEAM: add a glad -->** | **<!-- TEAM: add a sad -->** | | **<!-- TEAM: add an Add -->** |

### 5.3 Sprint 3 retro (to hold 2026-06-05)

**<!-- TEAM: fill in after sprint 3 closes. Same Glad/Sad/Mad/Add
format. Worth recording: how the Mon client meeting went, whether
the edge benchmark hardware actually showed up, how the interim
demo went. -->**

## 6. Time tracking

Hours per member, accumulated across sprints. The team logs hours
in Toggl / spreadsheet **<!-- TEAM: confirm tool -->** and aggregates
weekly.

| Member | Sprint 1 | Sprint 2 | Sprint 3 | Sprint 4 | Sprint 5 | Total |
|---|---:|---:|---:|---:|---:|---:|
| Sousa Rodrigo | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** |
| Chekhun Maksym | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** |
| Kattan Hamzzah | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** |
| Rooms Maxim | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** |
| **Team total** | | | | | | |

Distribution chart (optional but recommended for the final
submission): a stacked bar of hours per person per sprint, plus a
per-work-package pie (Data+Model vs Application vs Ceremony).

## 7. Risk log

| # | Risk | Likelihood | Impact | Mitigation | Status |
|---|---|---|---|---|---|
| R1 | PAPI 06 height + datum unconfirmed by 2026-06-03 | Med | High (angles unreliable) | Mon 2026-06-01 client meeting; use FAA defaults as fallback | active — see meeting-reports/2026-06-01-geometry-closure.md |
| R2 | Edge-device hardware unavailable before final | Med | Med (LR1B band capped) | Order Raspberry Pi 5 Mon; fall back on a school NUC if needed | active |
| R3 | INT8 ONNX path fails on CPU (`ConvInteger(10)`) | Realised | Low (FP32 path works) | Document as measured failure; fall back FP32 in demo | closed (documented) |
| R4 | App.jsx monolith grows un-maintainable | Low | Low | Modularisation card in sprint 4 | active |
| R5 | A team member loses days to illness | Low | Med | Cross-training: every speaker briefs one backup speaker | active |
| R6 | Coaches lose access to Trello / repo | Low | High (LR3 risk) | Re-verify access Mon 2026-06-01 | active |

## 8. Decision log

| Date | Decision | Driver | Tradeoff accepted |
|---|---|---|---|
| 2026-05-19 | Two YOLO classes, transition computed geometrically | Transition labels too rare and ill-defined to learn | Requires drone GPS metadata; falls back to white/red without |
| 2026-05-19 | Single-airport dataset (EDNY only) | No second airport drop planned by client | Cross-airport generalisation out of scope for v1.0 |
| 2026-05-22 | Postgres over SQLite | Concurrent connections in Docker compose | Heavier image, requires init script |
| 2026-05-26 | YOLO 26n over 26s/26m as primary | Real-time target ≥ 10 fps on edge | Lower accuracy ceiling than 26m |
| 2026-05-27 | Audit-tracked fix taxonomy | Need to triage 39 issues from independent code review | Some noise added to commit messages |
| 2026-05-28 | Drop fabricated "edge memory: 412 MB" metric | Honest visuals principle (design doc §1) | Live Demo loses a card until real numbers exist |

## 9. Communication and meeting cadence

| Channel | Frequency | Purpose |
|---|---|---|
| Daily standup | M-F 09:30, Discord | Yesterday / today / blockers |
| Sprint review | Fri afternoon | Demo what landed, plan next week |
| Sprint retro | Fri after review | Glad / Sad / Mad / Add |
| Client weekly | Tue 14:30 (var.), online | Status + open questions |
| Async log | Continuous, BigBrain | Decisions, audits, open questions |

### Client meetings held

| # | Date | Topic | Report |
|---|---|---|---|
| 1 | 2026-05-18 | Project kickoff | `meeting-reports/2026-05-18-kickoff.md` |
| 2 | 2026-05-19 | Dataset confirmation + scope | `meeting-reports/2026-05-19-dataset-confirmation.md` |
| 3 | 2026-05-26 | Geometry, lamp coords, transitions | `meeting-reports/2026-05-26-geometry.md` |
| 4 | 2026-06-01 | PAPI 06 closure, set-angles, datum | `meeting-reports/2026-06-01-geometry-closure.md` (after the meeting) |
| 5 | **<!-- TEAM: schedule with Daoud — recommended week of 15-19 June, before final --></sub>** | Final hand-off | t.b.d. |

## 10. Tools

| Tool | Use |
|---|---|
| Trello | Sprint board, daily standup notes |
| GitHub | Version control, PRs, Actions CI |
| BigBrain (Obsidian-style vault) | Decision log, audits, open questions, meeting summaries |
| Discord | Daily standup channel, async chat |
| Toggl **<!-- TEAM: confirm -->** | Time tracking |
| pandoc + LaTeX | Markdown → PDF for deliverables |
| Figma / Canva **<!-- TEAM: confirm tool for the poster -->** | A3 poster |
| Docker | Reproducible local + jury deployment |

## 11. Reflection — process learnings

Two pieces of process the team would take into a next project:

1. **Audit-on-fixed-cadence.** The 2026-05-27 audit produced 39
   findings; 36 closed in two sprints. The pattern of "independent
   audit → tagged backlog → close in priority order" worked because
   the tags survived in commit messages, so traceability is
   automatic. The team will repeat this on every project.

2. **Same-day user-testing iteration.** Holding round 2 the same
   afternoon as round 1 (after the morning's fixes landed) was the
   single biggest leverage point in sprint 2. The pattern only works
   if (a) the test plan is written before round 1 starts, and (b)
   the test team is the same people doing the fixes. Both were true.

**<!-- TEAM: optional third point — anything from the sprint 3 retro
worth carrying forward. -->**

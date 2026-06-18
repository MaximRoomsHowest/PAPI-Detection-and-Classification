---
title: "PAPI Lights Detection and Classification — Project Management Summary"
subtitle: "Sprint backlog · burndown · retrospectives · time tracking"
date: "Final — 19 June 2026"
mainfont: "Calibri"
fontsize: 11pt
geometry: "a4paper, margin=2cm"
---

# Project Management Summary

## At a glance

- **Project** — PAPI Lights Detection and Classification: AI-assisted approach-light verification
- **Client** — Intersoft Electronics Services BV (Daoud Uahabi)
- **Team** — Sousa Rodrigo · Chekhun Maksym · Kattan Hamzzah · Rooms Maxim
- **Duration** — 18 May → 19 June 2026 (five one-week sprints)
- **Board** — Trello · **Code** — GitHub + Actions CI · **Hours** — Toggl

## 1. Sprint backlog

Work is tracked on Trello, moving through **Product Backlog → Sprint
Backlog → In Progress → Testing → Done**, planned across five weekly
sprints. At final delivery, the committed scope was complete:
**162 of 162 story points done**. A 9-point drone-simulation idea was
kept as a stretch goal and was not included in the final scope.

![](charts/trello-board.png)

| Sprint | Week | Focus |
|---|---|---|
| 1 | 18–22 May | Data ingest + camera calibration |
| 2 | 25–29 May | Backend + frontend MVP |
| 3 | 1–5 Jun | Client features + interim prep |
| 4 | 8–12 Jun | Final polish |
| 5 | 15–19 Jun | Submission |

Board: <https://trello.com/b/iLrmBsgI/papi-industry-project-sprints>

## 2. Burndown chart

The burndown below is derived from the story points on the Trello
cards. The dashed line is the ideal path. The solid line shows the
actual remaining points after each sprint:

- Start: 162
- Sprint 1: 111
- Sprint 2: 76
- Sprint 3: 51
- Sprint 4: 31
- Sprint 5: 0

The final 31 points were completed in Sprint 5. These covered testing,
manuals, and the final presentation.

![](charts/burndown.png)

## 3. Retrospectives

Format: **Glad / Sad / Mad / Add**.

### Sprint 1 (2026-05-22)

| Glad | Sad | Mad | Add |
|---|---|---|---|
| Calibration worked first try (~6 px) | Auto-labelling took longer than estimated | Dataset confirmation came Monday, not Friday | Ask the client for blockers the Friday before |
| Label spec landed early | ZoomCamera focal length missing | | Add a "client blockers" column to Trello |

### Sprint 2 (2026-05-29)

| Glad | Sad | Mad | Add |
|---|---|---|---|
| Backend + frontend wired in two days | User testing found 6 demo blockers | A Plotly module issue cost an afternoon | Run user testing earlier in the sprint |
| Docker stack hardened | App.jsx grew too large | | Split App.jsx |
| CI green by Wednesday | | | |

### Sprint 3 (2026-06-05)

| Glad | Sad | Mad | Add |
|---|---|---|---|
| Client-requested features were added before the interim | The angle calculation needed a full rebuild | The final demo scope kept changing | Keep geometry assumptions visible in the UI and docs |
| Interim demo flow was stable | Some model work moved into the final weeks | | Test with real user flows earlier |

### Sprint 4 (2026-06-12)

| Glad | Sad | Mad | Add |
|---|---|---|---|
| Corrected angle calculation matched the client reference | Transition data was limited | Weather robustness remained uneven | Keep clear-weather and adverse-weather results separate |
| Insights and History became more useful | Cloud deployment still needed follow-up | | Make model choices visible in the app |

### Sprint 5 (2026-06-19)

| Glad | Sad | Mad | Add |
|---|---|---|---|
| Final documents, poster, and presentation were completed | Some edge-hardware numbers could not be measured without client hardware | The final package took longer than expected | Freeze deliverable content earlier next time |
| The project was handed over with manuals and source code | | | Keep a handover checklist from sprint 1 |

## 4. Time tracking

Each member logged their hours in Toggl, tagged by work area. The
figures below cover the full project period.

| Member | Hours |
|---|---:|
| Sousa Rodrigo | 148.2 |
| Kattan Hamzzah | 146.8 |
| Rooms Maxim | 151.5 |
| Chekhun Maksym | 150.5 |
| **Team total** | **597.0** |

![](charts/hours-by-member.png)

![](charts/hours-by-workarea.png)

The load is even across the team (147–152 hours each). Most time went
to Data & AI: the dataset, labelling, and model work.

---
title: "PAPI Lights Detection and Classification — Project Management Summary"
subtitle: "Sprint backlog · burndown · retrospectives · time tracking"
date: "Interim — 3 June 2026"
mainfont: "Calibri"
fontsize: 11pt
geometry: "a4paper, margin=2cm"
---

# Project Management Summary

<!--
Internal note (not rendered): source for the project-management summary.
Fill the TEAM markers (burndown, weeks 3–5 hours) before each export.
Find them with: Select-String -Path 05-project-management-summary.md -Pattern "TEAM"
-->

## At a glance

- **Project** — PAPI Lights Detection and Classification: AI-assisted approach-light verification
- **Client** — Intersoft Electronics Services BV (Daoud Uahabi)
- **Team** — Sousa Rodrigo · Chekhun Maksym · Kattan Hamzzah · Rooms Maxim
- **Duration** — 18 May → 19 June 2026 (five one-week sprints)
- **Board** — Trello · **Code** — GitHub + Actions CI · **Hours** — Toggl

## 1. Sprint backlog

Work is tracked on Trello, moving through **Product Backlog → Sprint
Backlog → In Progress → Testing → Done**, planned across five weekly
sprints. At the interim: 19 cards in the product backlog, 1 in the
sprint backlog, 1 in progress, 1 in testing, and **29 done**.

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

*Burndown chart to be added before submission.*

<!-- TEAM: the board has no burndown power-up installed yet (only a backlog
card to add one), so there is no chart to pull. Install a free burndown
power-up on the board (e.g. Corrello or Screenful) and screenshot the chart
it generates, or export the cards and plot remaining story points per day.
Take the numbers from the board; do not invent them. -->

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

### Sprint 3 (to hold 2026-06-05)

*To be filled in after the retro.*

## 4. Time tracking

Each member logs their hours in Toggl, tagged by work area. The figures
cover the period logged so far — weeks 1–2 (sprints 1 and 2). Weeks 3–5
follow as those exports come in. Source: `docs/timetrack-*.pdf`.

| Member | Hours (weeks 1–2) |
|---|---:|
| Sousa Rodrigo | 86.8 |
| Kattan Hamzzah | 84.0 |
| Rooms Maxim | 79.3 |
| Chekhun Maksym | 71.2 |
| **Team total** | **321.4** |

![](charts/hours-by-member.png)

![](charts/hours-by-workarea.png)

The load is even across the team (71–87 hours each). Most time went to
Data & AI — the dataset, labelling and model work — where the hardest
problems were.

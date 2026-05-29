---
title: "Client Meeting Report #2 — Dataset Confirmation"
date: "2026-05-19"
client: "Intersoft Electronics Services BV"
client_contact: "Daoud Uahabi"
team: "Sousa Rodrigo · Chekhun Maksym · Kattan Hamzzah · Rooms Maxim"
duration: "<!-- TEAM: e.g. 30 min -->"
location: "<!-- TEAM: online (Teams / Zoom) or on-site -->"
mainfont: "Calibri"
fontsize: 10pt
geometry: "a4paper, margin=2cm"
---

# Client Meeting Report #2 — Dataset Confirmation (2026-05-19)

> **Template — fill from the team's notes before the interim upload.** This
> report closes kickoff actions A1 (dataset drop) and A2 (EXIF / DJI XMP
> extraction + loader decision) and the kickoff open questions Q1 (how
> coordinates are embedded) and Q2 (label format). Only the agenda below is
> pre-filled from the kickoff record; every decision/answer is a `<!-- TEAM -->`
> marker — do not invent outcomes. If the dataset handoff happened async rather
> than as a live meeting, say so here.

## Attendees

- **Client (Intersoft Electronics Services BV)**: Daoud Uahabi
- **Team (Howest CTAI)**: Sousa Rodrigo, Chekhun Maksym, Kattan Hamzzah, Rooms Maxim
- **Supervisor**: <!-- TEAM: present? Y/N + name -->

## Agenda

1. Dataset drop received (kickoff action A1) — scope, size, folder layout.
2. Coordinate-embedding mechanism confirmed (kickoff Q1 — overlay / EXIF / XMP / sidecar).
3. Label format confirmed (kickoff Q2 — frame-level / per-lamp bbox / polygons).
4. EXIF + DJI XMP extraction result and the loader decision (kickoff action A2).
5. Day vs night coverage and any gaps to flag.

## Decisions and clarifications captured

### Dataset drop (A1)

- **What was received**: <!-- TEAM: flight count, image count, total size, folder structure -->
- **Access mechanism**: <!-- TEAM: download link / drive / physical media -->

### Coordinate embedding (Q1)

- **Confirmed mechanism**: <!-- TEAM: overlay text / EXIF GPS / DJI XMP / sidecar -->
- **Loader implication**: <!-- TEAM: how the pipeline reads it (links to packages/papi/src/papi/metadata.py) -->

### Label format (Q2)

- **Confirmed format**: <!-- TEAM: frame-level / per-lamp bbox / polygon; CVAT workflow -->

### EXIF / XMP extraction + loader decision (A2)

- **Result**: <!-- TEAM: which tags were present, what the loader now expects -->

## Open questions still outstanding

| # | Question | Owner | Status |
|---|---|---|---|
| <!-- TEAM --> | <!-- TEAM: carry over any still-open kickoff item (e.g. real-time/FPS target Q4) --> | <!-- TEAM --> | <!-- TEAM --> |

## Actions

| # | Action | Owner | Due |
|---|---|---|---|
| <!-- TEAM --> | <!-- TEAM: e.g. finalise the loader mechanism, draft sprint-1 backlog --> | <!-- TEAM --> | <!-- TEAM --> |

## Cross-references

- Previous report: `meeting-reports/2026-05-18-kickoff.md`
- Dataset summary: BigBrain `02-courses/industry-project/intersoft-papi-dataset-2026-04-28-29-summary.md`
- Project hub: `03-projects/intersoft-papi-detection.md`

## Sign-off

Notes verified by **<!-- TEAM: minute-taker -->** and shared with the team +
supervisor on 2026-05-19.

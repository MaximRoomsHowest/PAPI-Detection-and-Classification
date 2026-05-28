---
title: "Client Meeting Report #2 — Geometry Sync"
date: "2026-05-26 14:00"
client: "Intersoft Electronics Services BV"
client_contact: "Daoud Uahabi"
team: "Sousa Rodrigo · Chekhun Maksym · Kattan Hamzzah · Rooms Maxim"
duration: "<!-- TEAM: e.g. 45 min -->"
location: "<!-- TEAM: online / on-site -->"
mainfont: "Calibri"
fontsize: 10pt
geometry: "a4paper, margin=2cm"
---

# Client Meeting Report #2 — Geometry Sync (2026-05-26)

## Attendees

- **Client (Intersoft Electronics Services BV)**: Daoud Uahabi
- **Team (Howest CTAI)**: Sousa Rodrigo, Chekhun Maksym, Kattan
  Hamzzah, Rooms Maxim
- **Supervisor**: <!-- TEAM: present? -->

## Agenda

1. Walk-through of the current frontend Results page.
2. Demo scope for the 03/06 interim (images vs videos).
3. Transition-detection methodology — colour classifier vs
   detector tracking.
4. Root cause of the broken angle calculation; receive missing
   geometry data.
5. Plan the third client meeting (Mon 01/06) and the path to the
   interim presentation.

## Frontend feedback (Results page)

- The Results-page graphs are **too small / cramped** in the
  current vertical-stack layout. Both the angle plots and the
  lights plots should be enlarged so each is comfortably readable
  in a live demo.
- The feedback is UI, not rendering-stack specific — applies
  whether the live view is the matplotlib desktop variant or the
  Plotly React frontend.

## Demo scope

- **Images-only is the demo target** for the 03/06 interim.
- **Video support is explicitly deferred** until images work
  cleanly end-to-end. The team will not spend interim-sprint
  budget on temporal smoothing or streaming.
- Implication for the sprint: prioritise an image-driven pipeline
  (load → detect → per-lamp classification → derive transition +
  angle → render Results).

## Open methodological choice — transition detection

- The team currently derives transitions from **per-lamp colour
  classification** (`white` / `red` / `transition`).
- The client noted an alternative: **lean on the detector's
  per-lamp state over time** — i.e. use detection-tracking to
  identify transitions, rather than a separate colour classifier.
- **Not a directive — a suggestion to evaluate.** Decision criteria
  the team will use:
  - Transition recall on the verification sample.
  - Transition-angle MAE.
  - False-transition rate.
- Both approaches will be measured before the interim and the
  preferred method will be the one with the better recall × MAE
  trade-off. To be reported on slide 5 of the interim deck.

## Geometry data received — root cause + fix

### Root cause of broken angles

The angle calculation was producing wrong numbers because the
client had not previously provided the **PAPI lamp coordinates**
and the **installation height**. The pipeline was approximating
with inferred / placeholder values.

### Per-lamp WGS84 coordinates (PAPI 06 — runway 06)

| Lamp (Punktnummer) | Longitude | Latitude |
|---|---|---|
| 1 | 9.504007 | 47.668810 |
| 2 | 9.503948 | 47.668881 |
| 3 | 9.503888 | 47.668951 |
| 4 | 9.503828 | 47.669021 |

**Height: not provided in this meeting** (open — see actions).

### Per-lamp WGS84 coordinates (PAPI 24 — runway 24)

| Lamp (Punktnummer) | Longitude | Latitude |
|---|---|---|
| 1 | 9.518154 | 47.673521 |
| 2 | 9.518214 | 47.673450 |
| 3 | 9.518274 | 47.673380 |
| 4 | 9.518333 | 47.673309 |

**Height: 461.37 (units assumed metres).** Datum unconfirmed —
WGS84 ellipsoidal vs AMSL is the open question.

### Risk note on datum

EXIF `GpsAltitude` from the DJI M4E is typically WGS84
ellipsoidal. Mixing datums silently shifts every angle by tens of
metres of vertical offset, which at standard standoff (~500 m)
biases elevation angles by enough to flip transition state. This
risk is logged in `configs/papi_edny.yaml` and will be closed at
the next client meeting.

## Decisions

| # | Decision | Effective |
|---|---|---|
| D1 | Enlarge Results-page graphs before the interim demo | Sprint 3 |
| D2 | Images-only for the interim demo; video deferred | Sprint 3 |
| D3 | Evaluate both transition-detection methods on the verification sample; decide before interim | Sprint 3 |
| D4 | Bind the angle code to the client-provided lamp coords; mark PAPI 06 height as provisional until confirmed | Immediate |

## Open questions to close at the next client meeting (2026-06-01)

| # | Question | Reason it matters |
|---|---|---|
| O1 | Height datum for the 461.37 figure (WGS84 ellipsoidal vs AMSL) | ±48 m geoid offset risk; biases every rwy-24 elevation angle |
| O2 | Lamp numbering convention (`Punktnummer 1` = nearest to runway or furthest?) | Locks the geometric order in the angle calculation |
| O3 | PAPI 06 installation height | Currently provisional; needed for night-flight angle accuracy |
| O4 | Commissioned set-angles per lamp per runway (the team is currently using FAA defaults [2.50°, 2.83°, 3.17°, 3.50°]) | Per-lamp state labels at transition boundaries shift once real angles are bound |

## Actions

| # | Action | Owner | Due |
|---|---|---|---|
| A1 | Bind lamp coords from `PAPI_Coords_Fred_DE.xlsx` into `configs/papi_edny.yaml` | Rodrigo | 2026-05-27 |
| A2 | Add `PAPI 06 height = provisional` warning to the angle code path | Rodrigo | 2026-05-27 |
| A3 | Enlarge Results-page graphs (Plotly layout pass) | Hamzzah | 2026-05-29 |
| A4 | Run transition-method comparison and write up a 1-page decision | Maksym | 2026-06-02 |
| A5 | Prepare the four open questions above as agenda for 2026-06-01 | Rodrigo | 2026-05-29 |
| A6 | Schedule client meeting #3 — confirmed 2026-06-01 14:30 | Rodrigo | 2026-05-26 ✓ |

## Cross-references

- BigBrain summary: `02-courses/industry-project/intersoft-client-meeting-2026-05-26-summary.md`
- Affected config: `configs/papi_edny.yaml` (lamp coords bound; height + datum + set-angle TODOs documented)
- Pipeline doc: `docs/pipeline.md` (calibration result, dual-runway resolution)

## Sign-off

Notes verified by **<!-- TEAM: minute-taker -->** and shared with
the team + supervisor on 2026-05-26.

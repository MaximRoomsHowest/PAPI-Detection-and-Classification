---
title: "Client Meeting Report #3 — Geometry Closure + Pre-Interim Sync"
date: "2026-06-01 14:30"
client: "Intersoft Electronics Services BV"
client_contact: "Daoud Uahabi"
team: "Sousa Rodrigo · Chekhun Maksym · Kattan Hamzzah · Rooms Maxim"
duration: "<!-- TEAM: e.g. 45 min -->"
location: "<!-- TEAM: online / on-site -->"
mainfont: "Calibri"
fontsize: 10pt
geometry: "a4paper, margin=2cm"
---

# Client Meeting Report #3 — Geometry Closure (2026-06-01)

> **Template for the meeting on Mon 2026-06-01 14:30.** Fill in
> answers and decisions immediately after the meeting; convert to
> PDF and include in the interim submission (03/06).

## Attendees

- **Client (Intersoft Electronics Services BV)**: Daoud Uahabi
- **Team (Howest CTAI)**: Sousa Rodrigo, Chekhun Maksym, Kattan
  Hamzzah, Rooms Maxim
- **Supervisor**: <!-- TEAM: present? -->

## Agenda

1. **Close the four open geometry questions** from the 2026-05-26
   meeting (see *Open questions* below). 20 min.
2. Show the rebuilt angle calculation working on a few frames per
   regime (day rwy 24 wide, night rwy 06 wide, day rwy 24 zoom).
   10 min.
3. Demo the enlarged Results-page graphs (per the 26/05 feedback).
   5 min.
4. Get the client's read on the transition-detection method
   choice. 5 min.
5. Brief the client on the 03/06 interim narrative + ask for
   anything they want highlighted. 5 min.

## Open questions to close

| # | Question | Client answer | Bind to |
|---|---|---|---|
| O1 | Height datum for 461.37 — WGS84 ellipsoidal vs AMSL? | **<!-- TEAM: capture verbatim -->** | `configs/papi_edny.yaml` comment + angle code path |
| O2 | Lamp numbering (`Punktnummer 1` = nearest runway or furthest?) | **<!-- TEAM: capture verbatim -->** | `packages/papi/src/papi/projection.py` lamp-order constant + label spec |
| O3 | PAPI 06 installation height (metres + datum)? | **<!-- TEAM: capture verbatim -->** | `configs/papi_edny.yaml runways.'06'.papi.light_*` |
| O4 | Commissioned set-angles per lamp per runway | **<!-- TEAM: capture verbatim -->** | `configs/papi_edny.yaml runways.*.papi.light_*.set_angle_deg` |

## Frontend demo result

**<!-- TEAM: capture client reaction to the enlarged Results-page
graphs. Note any further UI tweaks requested. -->**

## Angle-rebuild demo result

The team showed angle outputs for at least one frame per regime:

- Day rwy 24 (Wide): **<!-- TEAM: angle + state -->**
- Night rwy 06 (Wide): **<!-- TEAM: angle + state -->**
- Day rwy 24 (Zoom): **<!-- TEAM: angle + state -->**

Client comment: **<!-- TEAM: capture verbatim -->**

## Transition-detection method decision

| Option | Transition recall | Transition-angle MAE | False-transition rate | Verdict |
|---|---|---|---|---|
| Colour classifier (current) | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** | |
| Detector tracking | **<!-- TEAM -->** | **<!-- TEAM -->** | **<!-- TEAM -->** | |

**Decision:** **<!-- TEAM: e.g. "Stick with colour classifier for
v1.0; revisit detector tracking in v1.1 because…" -->**

Client comment on the decision: **<!-- TEAM: capture verbatim -->**

## Interim narrative

The team walked the client through the 13-slide interim deck
(`docs/deliverables/03-interim-presentation-outline.md`). Client
input:

- Things to emphasise: **<!-- TEAM -->**
- Things to downplay: **<!-- TEAM -->**
- Client willing to attend live (Wed 03/06 08:30): **<!-- TEAM:
  Y/N -->**

## Decisions

| # | Decision | Effective |
|---|---|---|
| D1 | Bind PAPI 06 height = **<!-- TEAM -->** m, datum **<!-- TEAM -->** | Immediate |
| D2 | Lamp numbering convention: `Punktnummer 1` = **<!-- TEAM -->** | Immediate |
| D3 | Set-angles: **<!-- TEAM: use commissioned values OR keep FAA defaults with caveat -->** | Immediate |
| D4 | Transition-detection method for v1.0: **<!-- TEAM -->** | Sprint 3 freeze |

## Actions

| # | Action | Owner | Due |
|---|---|---|---|
| A1 | Update `configs/papi_edny.yaml` with confirmed values | Rodrigo | 2026-06-01 evening |
| A2 | Re-run angle verification on the test sample with confirmed values; record numbers in `docs/edge-benchmark.md` accuracy delta | Maksym | 2026-06-02 |
| A3 | Update interim slide 6 with the new model-eval numbers | Rodrigo | 2026-06-02 |
| A4 | Update `01-design-document.md §11` and the README with confirmed geometry note | Hamzzah | 2026-06-02 |
| A5 | Send interim deck (PDF) to Daoud for review by Wed morning | Rodrigo | 2026-06-02 |

## Risks raised or resolved

- **R1 (resolved if D1–D3 close):** PAPI 06 angles were provisional.
  After this meeting they become bound.
- **R2 (open):** real-time inference target is still ~2 fps on CPU;
  edge benchmark on Raspberry Pi 5 / Jetson Orin Nano scheduled
  for sprint 4. Reported in the interim as honest in-flight.

## Cross-references

- Previous meeting: `meeting-reports/2026-05-26-geometry-sync.md`
- Affected config: `configs/papi_edny.yaml`
- Affected code: `packages/papi/src/papi/projection.py`,
  `apps/backend/app/services/angle.py`
- Interim deck: `docs/deliverables/03-interim-presentation-outline.md`

## Sign-off

Notes captured live by **<!-- TEAM: minute-taker -->**, verified
with Daoud Uahabi within 24 hours of the meeting, and circulated
to the team + supervisor.

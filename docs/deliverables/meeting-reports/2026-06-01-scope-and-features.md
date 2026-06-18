---
title: "Client Meeting Report #3 — Scope, Features & Angle Method"
date: "2026-06-01 14:30"
client: "Intersoft Electronics Services BV"
client_contact: "Daoud Uahabi"
team: "Sousa Rodrigo · Chekhun Maksym · Kattan Hamzzah · Rooms Maxim"
duration: "Not recorded"
location: "Online meeting"
mainfont: "Calibri"
fontsize: 10pt
geometry: "a4paper, margin=2cm"
---

# Client Meeting Report #3 — Scope, Features & Angle Method (2026-06-01)

Third client meeting, two days before the interim. As usual we showed
the current build and then took Daoud's feedback — this time four
concrete asks, plus two diagrams defining how the viewing angle should
be computed.

## Attendees

- **Client (Intersoft Electronics Services BV)**: Daoud Uahabi
- **Team (Howest CTAI)**: Sousa Rodrigo, Chekhun Maksym, Kattan
  Hamzzah, Rooms Maxim
- **Supervisor**: not recorded in the meeting notes

## Agenda

1. Demo of the current build.
2. Client feedback and requests.
3. The angle-calculation method.

## What the client asked

1. **Two runways, with room to add more.** EDNY has a PAPI at each end
   of the strip (06 and 24). We scoped this as **runway selection** —
   the user picks the runway and the system uses its geometry. We won't
   detect two runways in one image: the 06 and 24 PAPIs sit at opposite
   ends of the strip and never appear together.
2. **Folder of images → one video.** A dropped folder is handled as one
   short clip: frames ordered, tracked over time, and written out as a
   single annotated video with one verdict — not separate image results.
3. **Behaviour when a lamp isn't detected.** A missing lamp now gets a
   named **"obscured"** state, shown in the results and charts. Limit:
   the two-class model can't tell a damaged lamp from a hidden one, so
   both read as "obscured".
4. **Which model for workstation WL051.** We couldn't answer without the
   machine's specs. **Daoud to send them** (CPU, GPU + VRAM, RAM). The
   most accurate model needs a GPU; on CPU it is slow (~0.4 fps), so a
   smaller model fits better there.

## The angle method

Daoud's two diagrams define it:

- The angle is `arctan(height / distance)` — drone height above the
  PAPI, and horizontal distance to the PAPI midpoint.
- Get both by converting the drone and PAPI positions to a common
  Earth-centred frame (ECEF), then to a local East-North-Up frame at
  the PAPI: distance is `sqrt(East² + North²)`, height is the Up value.

Our current code approximates this with a simpler formula and mixes
height references. We'll rebuild it the East-North-Up way, which also
settles the open question about the 461.37 m height figure.

## Built the same day

Three of the asks were implemented and verified right after the meeting
(tests pass, demo checked): runway selection, folder → video, and the
"obscured" state. The angle rebuild is a follow-up.

## Open items

| # | Action | Owner | Due |
|---|---|---|---|
| A1 | Send the WL051 specs (CPU / GPU + VRAM / RAM) | Daoud | next contact |
| A2 | Rebuild the angle with the East-North-Up method | Rodrigo | sprint 4 |
| A3 | Confirm PAPI 06 height, the 461.37 m reference, and lamp numbering | Daoud | next contact |
| A4 | Decide how a user-added runway supplies its geometry | Team | sprint 4 |

## Cross-references

- Previous meeting: `meeting-reports/2026-05-26-geometry-sync.md`
- Config `configs/papi_edny.yaml`; code `apps/backend/app/services/angle.py`

## Sign-off

Notes by **Rodrigo Sousa**, confirmed with Daoud Uahabi and shared
with the team.

---
title: "Client Meeting Report #4 — Progress, Corrected Angle & Transition Model"
date: "2026-06-08 14:30"
client: "Intersoft Electronics Services BV"
client_contact: "Daoud Uahabi"
team: "Sousa Rodrigo · Chekhun Maksym · Kattan Hamzzah · Rooms Maxim"
duration: "Not recorded"
location: "Online meeting"
mainfont: "Calibri"
fontsize: 10pt
geometry: "a4paper, margin=2cm"
---

# Client Meeting Report #4 — Progress, Corrected Angle & Transition Model (2026-06-08)

The first meeting after the interim presentation. We demonstrated the
latest build, showed the corrected angle calculation, and reported that
the transition model is now trained — and asked the client for feedback
on the model.

## Attendees

- **Client (Intersoft Electronics Services BV)**: Daoud Uahabi
- **Team (Howest CTAI)**: Sousa Rodrigo, Chekhun Maksym, Kattan
  Hamzzah, Rooms Maxim
- **Supervisor**: not recorded in the meeting notes

## Agenda

1. Demo of the latest app updates.
2. The corrected angle calculation.
3. Transition-model status.
4. Request for client feedback on the model.

## What we showed

1. **App updates.** We walked the client through the latest changes to
   the application and asked for feedback on the model.
2. **Corrected angle calculation.** We showed the rebuilt angle output.
   The earlier method was wrong; the new East-North-Up calculation now
   matches the client's own reference values (agreement within about
   0.02° on the runway-24 datum).
3. **Transition model.** We reported that the model which detects each
   lamp's red-to-white change had been trained, and described the
   directions we are exploring to improve it.

## Open items

| # | Action | Owner | Due |
|---|---|---|---|
| A1 | Give feedback on the model | Daoud | next contact |
| A2 | Continue improving the transition model | Rodrigo / team | sprint 5 |
| A3 | Confirm whether the corrected angle is final, or still needs the runway-06 set angles | Daoud | next contact |

## Cross-references

- Previous meeting: `meeting-reports/2026-06-01-scope-and-features.md`
- Code `apps/backend/app/services/angle.py`; transition work `docs/transition/`

## Sign-off

Notes by **Rodrigo Sousa**, confirmed with Daoud Uahabi and shared
with the team.

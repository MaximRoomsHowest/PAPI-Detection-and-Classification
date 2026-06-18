---
title: "Client Handover Email"
subtitle: "Proof of handover · Howest Industry Project 2026"
mainfont: "Calibri"
fontsize: 10pt
geometry: "a4paper, margin=2cm"
---

> Final handover email text for Daoud Uahabi at Intersoft Electronics
> Services BV. Save the sent message and Daoud's acknowledgement as
> PDFs and keep both on file as proof of handover.

## Handover checklist

- Repository link included.
- Source ZIP attached or linked.
- User manual included.
- Installation manual included.
- Architecture / components overview included.
- Model registry and configuration paths named.
- The team stays reachable for 30 days after handover.

---

## Email body (English)

```
From:    Sousa Rodrigo <rodrigo.sousa@student.howest.be>
To:      Daoud Uahabi <daoud.uahabi@intersoft-electronics.com>
Cc:      Chekhun Maksym, Kattan Hamzzah, Rooms Maxim,
         [supervisor email]
Bcc:     (none)
Subject: PAPI Lights Detection and Classification — Howest Industry Project handover

Hi Daoud,

A short message to formally hand PAPI Lights Detection and Classification over to Intersoft
Electronics Services BV. We've reached the end of the Howest
Industry Project (final presentation Friday 19/06), and the
codebase, model and documentation are now yours to use, extend or
archive as you see fit.

Everything you need is in the GitHub repository:

  https://github.com/MaximRoomsHowest/PAPI-Detection-and-Classification

Specifically:

  • Source code            — main branch, tagged `v1.0-final`
  • Source ZIP             — attached (papi-vision-source-v1.0-final.zip)
  • User manual            — docs/user-manual.md
  • Installation manual    — docs/installation-manual.md
  • Architecture overview  — docs/architecture-overview.md
  • Design document        — docs/deliverables/01-design-document.md
  • Edge benchmark report  — docs/edge-benchmark.md (incl. cost projection)
  • Model registry         — models/MODELS.md
  • Configs                — configs/papi_edny.yaml (lamp coords as you
                             provided on 2026-05-26 and 2026-06-01)

To start the application from a clean machine:

  git clone https://github.com/MaximRoomsHowest/PAPI-Detection-and-Classification
  cd PAPI-Detection-and-Classification
  cp .env.example .env       # adjust PAPI_API_KEY and PAPI_ENV=production
  docker compose up -d --build
  # then open http://localhost:5173 (or your reverse-proxy hostname)

Five things worth flagging:

  1. `configs/papi_edny.yaml` binds the current runway geometry:
     rwy 24 uses the validated 461.37 m reference, and rwy 06 uses
     the data-analysis branch's 461.37 m working reference. The
     464.988 m value in that branch is client drone EXIF/MRK altitude
     metadata, not lamp height. Lamp order and commissioned set angles
     still need binding.

  2. The detector is YOLO 26s, fine-tuned on the EDNY dataset only.
     Generalisation to other airports requires a fresh
     papi_*.yaml geometry file plus retraining on capture from
     the new site.

  3. The final package includes measured laptop CPU and GPU reference
     numbers. Intersoft's WL051 hardware specs were not available
     during the project, so a final recommendation for that exact
     workstation still needs to be confirmed on Intersoft hardware.

  4. Production deployment requires PAPI_ENV=production and a
     PAPI_API_KEY set in .env. The installation manual covers
     HTTPS termination via Caddy in the Production section.

  5. The serving model is models/serving/best.pt (PyTorch), which
     runs on any CPU or GPU. For a ~1.5x CPU speedup, enable the
     bundled OpenVINO export by setting BACKEND_INSTALL_ACCEL=true
     in .env and rebuilding. There is no working INT8/ONNX build at
     present (the earlier INT8 export is retired and CPU-incompatible
     - see models/MODELS.md section 3.2.1); revisit quantisation once
     an edge target is fixed.

We are happy to answer questions for the next 30 days at the
addresses above — no commercial commitment, just a courtesy
window for getting the deployment running on Intersoft hardware.

A printed copy of the user manual + installation manual is in
the binder we leave with you after Friday's presentation.

Thank you for the project, the time you put into the geometry
meetings, and the dataset. It was a great five weeks.

Best regards,

Sousa Rodrigo
on behalf of the PAPI Lights Detection and Classification team
Sousa Rodrigo · Chekhun Maksym · Kattan Hamzzah · Rooms Maxim
Howest CTAI, Bachelor 2025-2026
```

## Email body (Nederlands, optional bilingual variant)

> Use only if the client prefers Dutch correspondence. Otherwise
> send the English version above as primary. The Dutch text below
> uses formal-second-person ("u") to match a business handover
> tone.

```
From:    Sousa Rodrigo <rodrigo.sousa@student.howest.be>
To:      Daoud Uahabi <daoud.uahabi@intersoft-electronics.com>
Subject: PAPI Lights Detection and Classification — Overdracht Howest Industry Project

Beste Daoud,

Met dit bericht dragen we PAPI Lights Detection and Classification formeel over aan
Intersoft Electronics Services BV. De code, het model en alle
documentatie staan vanaf vandaag tot uw beschikking — om te
gebruiken, uit te breiden of te archiveren naar eigen inzicht.

Alles is beschikbaar in de GitHub-repository:

  https://github.com/MaximRoomsHowest/PAPI-Detection-and-Classification

Concreet:

  • Broncode               — branch main, tag `v1.0-final`
  • Broncode (ZIP)         — in bijlage
  • Gebruikershandleiding  — docs/user-manual.md
  • Installatiehandleiding — docs/installation-manual.md
  • Architectuuroverzicht  — docs/architecture-overview.md
  • Ontwerpdocument        — docs/deliverables/01-design-document.md
  • Edge-benchmark         — docs/edge-benchmark.md
  • Modelregister          — models/MODELS.md
  • Configuratie           — configs/papi_edny.yaml

Om de applicatie van een lege machine op te starten:

  git clone <repo>
  cd PAPI-Detection-and-Classification
  cp .env.example .env       # PAPI_API_KEY + PAPI_ENV=production
  docker compose up -d --build

We blijven de komende 30 dagen bereikbaar voor vragen via de
adressen in de Cc — zonder commerciële verplichtingen, gewoon
om u te helpen bij het deployen op Intersoft-hardware.

Met vriendelijke groet,

Sousa Rodrigo
namens het PAPI Lights Detection and Classification-team
```

## Acknowledgement to capture

Ask Daoud to reply with **"Received and accepted"** so the team has
a written confirmation. Keep his reply alongside the sent email on
file — both saved as PDF.

Filename convention for the records:

- `handover-email-sent-2026-06-17.pdf`
- `handover-email-received-2026-06-1X.pdf`

## Cross-references

- Source of truth for what was handed over: `README.md` (this folder)
- Model registry / lineage: `../../models/MODELS.md`

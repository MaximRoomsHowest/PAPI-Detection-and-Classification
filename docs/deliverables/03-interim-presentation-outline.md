---
title: "Interim Presentation — Record"
subtitle: "PAPI Lights Detection and Classification · 3 June 2026"
mainfont: "Calibri"
fontsize: 10pt
geometry: "a4paper, margin=2cm"
---

# Interim Presentation — Record

This file records the interim presentation content. It is kept for
traceability. The final delivery is documented in
`09-final-presentation-outline.md`.

## Purpose

The interim presentation showed progress after the first three weeks:

- the project problem and client context;
- the first working detection pipeline;
- the frontend demo flow;
- the early project-management evidence;
- the risks that still needed work before final delivery.

## Content Summary

| Section | Content |
|---|---|
| Problem | PAPI lights help pilots judge glidepath using red/white lamp patterns. |
| Dataset | EDNY drone imagery with day and night data. |
| Labelling | Geometry-assisted labelling and CVAT correction. |
| Model | First YOLO-based lamp detector and state classifier. |
| Application | Early web demo for image analysis. |
| Project management | Trello board, sprint planning, and time tracking. |
| Risks | Daylight glare, angle calculation, transition detection, and edge performance. |

## Outcome

The interim presentation confirmed that the team had a working path:

1. ingest drone imagery;
2. detect PAPI lamps;
3. classify red/white state;
4. show the result in the application;
5. continue refining angle calculation and transition handling.

The final deck replaced this progress story with the delivered product
story.

# PAPI Lights Detection and Classification — Deliverables Index

> Documentation index for the deliverables package. Each row maps a
> deliverable to (a) the source file in this folder, (b) whether it
> belongs to the interim or final package, (c) status.
>
> Render every deliverable to PDF in one shot:
> ```powershell
> pwsh scripts\build-deliverables.ps1
> ```
> The current final exports are in `docs/deliverables/_build/`.

## Interim deliverables

| # | Deliverable | Source file | Status |
|---|---|---|---|
| 1 | Interim presentation | `03-interim-presentation-outline.md` | archived record |
| 2 | Project-management summary | `05-project-management-summary.md` | final source |
| 3 | Meeting reports (1 PDF, 5 reports) | `meeting-reports/*.md` | ready — kickoff (05-18) / geometry sync (05-26) / scope & features (06-01) / week-4 check-in (06-08) / handover (06-15) |
| 4 | MCT functional analysis | N/A (team is CTAI) | not applicable |

## Final deliverables

| # | Deliverable | Source file | Status |
|---|---|---|---|
| 1 | Final presentation + proof of handover | `_build/PAPI-Presentation.pdf` + `_build/PAPI-Client-Handover-Email.pdf` | complete |
| 2 | Weekly meeting reports bundle (≥5 weeks) | `_build/PAPI-Client-Meeting-Reports.pdf` | complete |
| 3 | User manual | `_build/PAPI-User-Manual.pdf` | complete |
| 4 | Installation manual | `_build/PAPI-Installation-Manual.pdf` | complete |
| 5 | Project-management documentation (final version) | `_build/PAPI-Project-Management-Summary.pdf` | complete |
| 6 | Promotional poster A3 | `_build/PAPI-Promotional-Poster-A3.pdf` | complete |
| 7 | Zip archive of source code | `_build/PAPI-source-code.zip` | complete |
| 8 | 1-page A4 "How technical components are connected" | `_build/PAPI-Technical-Components-Overview.pdf` | complete |
| 9 | MCT functional analysis | N/A (team is CTAI) | not applicable |

## Additional reference documents

| # | Deliverable | Source file | Status |
|---|---|---|---|
| A | Design document | `_build/PAPI-Design-Document.pdf` | complete |
| B | Edge benchmark | `../edge-benchmark.md` | final status documented |
| C | Model registry / lineage | `../../models/MODELS.md` | complete |
| D | Alternative-model comparison | `_build/PAPI-Model-Comparison.pdf` | complete |
| E | Frontend test suite | `apps/frontend` tests | complete in repo validation |

## File-numbering convention

Two-digit prefix on every file so `ls` sorts them in presentation order.
`00-` reserved for this index.

| Prefix | Purpose |
|---|---|
| `01` | Design document |
| `02` | (reserved) |
| `03` | Interim presentation outline |
| `04` | Components overview A4 |
| `05` | Project management summary |
| `06` | Model comparison |
| `07` | (reserved) |
| `08` | Promotional poster brief |
| `09` | Final presentation outline |
| `10` | Client handover email |
| `meeting-reports/` | One file per meeting, named `YYYY-MM-DD-topic.md` |

## How to use this folder

1. Treat the files in `_build/` as the submission artifacts.
2. Treat the Markdown files as editable source notes.
3. If a source changes, regenerate the matching PDF before upload.

## Source links (do not duplicate in deliverables)

These are referenced by the deliverables but live elsewhere — keep
the canonical copy in one place and link to it:

- **Project overview**: `docs/final-report.md` and `docs/architecture-overview.md`
- **Trello board**: <https://trello.com/b/iLrmBsgI/papi-industry-project-sprints>
- **GitHub repo**: <https://github.com/MaximRoomsHowest/PAPI-Detection-and-Classification>

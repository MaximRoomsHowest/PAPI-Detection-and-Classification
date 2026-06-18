# PAPI Lights Detection and Classification — Deliverables Index

> Documentation index for the deliverables package. Each row maps a
> deliverable to (a) the source file in this folder, (b) whether it
> belongs to the interim or final package, (c) status.
>
> Render every deliverable to PDF in one shot:
> ```powershell
> pwsh scripts\build-deliverables.ps1
> ```
> The script walks `docs/deliverables/` recursively, honours each
> file's YAML front-matter (A4 / A3 geometry, fonts, margins), and
> warns about any unfilled `<!-- TEAM: ... -->` markers before
> the package is assembled. See `scripts/build-deliverables.ps1` for
> the prerequisites (pandoc + a LaTeX engine).

## Interim deliverables

| # | Deliverable | Source file | Status |
|---|---|---|---|
| 1 | Interim presentation | `03-interim-presentation-outline.md` (content) → team styles into slides | drafting |
| 2 | Project-management summary | `05-project-management-summary.md` | template + team to fill |
| 3 | Meeting reports (1 PDF, 5 reports) | `meeting-reports/*.md` | ready — kickoff (05-18) / geometry sync (05-26) / scope & features (06-01) / week-4 check-in (06-08) / handover (06-15) |
| 4 | MCT functional analysis | N/A (team is CTAI) | not applicable |

## Final deliverables

| # | Deliverable | Source file | Status |
|---|---|---|---|
| 1 | Final presentation + proof of handover | `09-final-presentation-outline.md` + `10-client-handover-email.md` | ✅ drafted |
| 2 | Weekly meeting reports bundle (≥5 weeks) | `meeting-reports/*.md` | ✅ 5 drafted (kickoff, geometry sync, scope & features, week-4 check-in, handover) |
| 3 | User manual | `../user-manual.md` → PDF | ✅ source ready, PDF export at handover |
| 4 | Installation manual | `../installation-manual.md` → PDF | ✅ source ready, PDF export at handover |
| 5 | Project-management documentation (final version) | `05-project-management-summary.md` updated | ✅ template; team fills numbers |
| 6 | Promotional poster A3 | `08-promotional-poster-brief.md` (brief) → design tool | ✅ brief; team executes in Figma/Canva |
| 7 | Zip archive of source code | generated at handover via `git archive` | trivial — handover day |
| 8 | 1-page A4 "How technical components are connected" | `04-components-overview-a4.md` | ✅ drafted |
| 9 | MCT functional analysis | N/A (team is CTAI) | not applicable |

## Additional reference documents

| # | Deliverable | Source file | Status |
|---|---|---|---|
| A | Design document | `01-design-document.md` | ✅ drafted |
| B | Edge benchmark — measurements + cost projection + conclusion | `../edge-benchmark.md` §5/§7/§8 | partial — §7/§8 structures done, §5 needs hardware |
| C | Model registry / lineage | `../../models/MODELS.md` | ✅ drafted |
| D | Alternative-model comparison | `06-model-comparison.md` | ✅ filled — measured numbers (2026-06-10) |
| E | Frontend test suite | `apps/frontend/{vitest config + .test.jsx}` | in progress (Track B) |

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

1. Each `.md` file is **content + structure**. It is not styled — the
   team applies house styling (Poppins, Intersoft navy `#00426e`) at
   PDF export time, either via the pandoc template above or by
   pasting into the team slide-deck template.
2. Where a deliverable needs team data (time tracking, burndown
   numbers, retro notes), the source `.md` has a
   `<!-- TEAM: fill in -->` marker. Search the folder for those
   markers to find every fill-in spot in one pass:
   ```powershell
   Select-String -Path docs\deliverables\*.md -Pattern "TEAM:"
   ```
3. After filling, regenerate PDFs for the deliverables package.

## Source links (do not duplicate in deliverables)

These are referenced by the deliverables but live elsewhere — keep
the canonical copy in one place and link to it:

- **Project overview**: `docs/final-report.md` and `docs/architecture-overview.md`
- **Trello board**: <https://trello.com/b/iLrmBsgI/papi-industry-project-sprints>
- **GitHub repo**: <https://github.com/MaximRoomsHowest/PAPI-Detection-and-Classification>

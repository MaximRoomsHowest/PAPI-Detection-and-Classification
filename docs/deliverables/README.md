# PAPI Vision — Deliverables Index

> Canonical "what's left for submission" board. Each row maps a Leho
> upload slot to (a) the source file in this folder, (b) the rubric
> criterion it serves, (c) interim vs final, (d) status.
>
> Render every deliverable to PDF in one shot:
> ```powershell
> pwsh scripts\build-deliverables.ps1
> ```
> The script walks `docs/deliverables/` recursively, honours each
> file's YAML front-matter (A4 / A3 geometry, fonts, margins), and
> warns about any unfilled `<!-- TEAM: ... -->` markers before
> submission. See `scripts/build-deliverables.ps1` for the
> prerequisites (pandoc + a LaTeX engine).

## Interim — Wed 2026-06-03 by 08:30 (Leho upload, 4 PDFs)

| # | Deliverable | Source file | Rubric | Status |
|---|---|---|---|---|
| 1 | Interim presentation | `03-interim-presentation-outline.md` (content) → team styles into slides | LR3 + LR2 | drafting |
| 2 | Project-management summary | `05-project-management-summary.md` | LR2 (required artifact) | template + team to fill |
| 3 | Meeting reports (3-4 PDFs) | `meeting-reports/*.md` | LR3 (required artifact) | drafting from BigBrain notes |
| 4 | MCT functional analysis | N/A (team is CTAI) | — | not applicable |

## Final — Fri 2026-06-19 by 08:30 (Leho upload, 8 items)

| # | Deliverable | Source file | Rubric | Status |
|---|---|---|---|---|
| 1 | Final presentation + proof of handover | `09-final-presentation-outline.md` + `10-client-handover-email.md` | LR3 | ✅ drafted |
| 2 | Weekly meeting reports bundle (≥5 weeks) | `meeting-reports/*.md` | LR3 | ✅ 3 drafted; team adds final-week meeting |
| 3 | User manual | `../user-manual.md` → PDF | LR1A | ✅ source ready, PDF export at submission |
| 4 | Installation manual | `../installation-manual.md` → PDF | LR1E | ✅ source ready, PDF export at submission |
| 5 | Project-management documentation (final version) | `05-project-management-summary.md` updated | LR2 (required artifact) | ✅ template; team fills numbers |
| 6 | Promotional poster A3 | `08-promotional-poster-brief.md` (brief) → design tool | LR3 | ✅ brief; team executes in Figma/Canva |
| 7 | Zip archive of source code | generated at submission via `git archive` | LR2 | trivial — submission day |
| 8 | 1-page A4 "How technical components are connected" | `04-components-overview-a4.md` | LR1E | ✅ drafted |
| 9 | MCT functional analysis | N/A (team is CTAI) | — | not applicable |

## Rubric-implied (not in Leho slots but needed for bands)

| # | Deliverable | Source file | Rubric | Status |
|---|---|---|---|---|
| A | Design document | `01-design-document.md` | LR1A (required artifact) | ✅ drafted |
| B | Edge benchmark — measurements + cost projection + conclusion | `../edge-benchmark.md` §5/§7/§8 | LR1D + LR1B (band-lift) | partial — §7/§8 structures done, §5 needs hardware |
| C | Model registry / lineage | `../../models/MODELS.md` | LR1D (band-lift) | ✅ drafted |
| D | Alternative-model comparison | `06-model-comparison.md` | LR1D 16+ | ✅ scaffolded; team fills numbers after training |
| E | Frontend test suite | `apps/frontend/{vitest config + .test.jsx}` | LR1A (band-lift) | in progress (Track B) |

## File-numbering convention

Two-digit prefix on every file so `ls` sorts them in presentation order.
`00-` reserved for this index.

| Prefix | Purpose |
|---|---|
| `01` | Design document (LR1A core) |
| `02` | (reserved) |
| `03` | Interim presentation outline |
| `04` | Components overview A4 |
| `05` | Project management summary |
| `06` | Model comparison (LR1D band-lift) |
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
   numbers, retro notes, P2P comments), the source `.md` has a
   `<!-- TEAM: fill in -->` marker. Search the folder for those
   markers to find every fill-in spot in one pass:
   ```powershell
   Select-String -Path docs\deliverables\*.md -Pattern "TEAM:"
   ```
3. After filling, regenerate PDFs and upload to Leho.

## Source links (do not duplicate in deliverables)

These are referenced by the deliverables but live elsewhere — keep
the canonical copy in one place and link to it:

- **Rubric**: BigBrain `02-courses/industry-project/industry-project-rubric-summary.md`
- **Deliverables spec**: BigBrain `02-courses/industry-project/industry-project-deliverables-summary.md`
- **Project hub**: BigBrain `03-projects/intersoft-papi-detection.md`
- **Audit backlog**: BigBrain `03-projects/papi-improvements-audit-2026-05-27.md`
- **Trello board**: <https://trello.com/b/iLrmBsgI/papi-industry-project-sprints>
- **GitHub repo**: <https://github.com/MaximRoomsHowest/PAPI-Detection-and-Classification>

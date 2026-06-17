# Documentation index

Start here. This folder holds the project documentation for **PAPI Lights
Detection and Classification**. Use the table below to find the right document
for what you need to do.

## For operators and engineers (start here)

| Document | Read it when you want to… |
|---|---|
| [`user-manual.md`](user-manual.md) | Run the app and interpret its output (drone operators, review engineers). |
| [`installation-manual.md`](installation-manual.md) | Install and deploy the system from scratch (Docker or native). |
| [`architecture-overview.md`](architecture-overview.md) | Understand how the components fit together and why. |

## Model and data reference

| Document | Covers |
|---|---|
| [`model-card.md`](model-card.md) | The serving model: intended use, metrics, and limitations. |
| [`../models/MODELS.md`](../models/MODELS.md) | Full model registry — lineage, training args, metrics, promotion/rollback. |
| [`data-card.md`](data-card.md) | Dataset composition, splits, and provenance. |
| [`label_spec.md`](label_spec.md) | Labelling taxonomy and per-lamp state semantics. |
| [`pipeline.md`](pipeline.md) | The auto-labelling data pipeline stages and their I/O. |
| [`edge-benchmark.md`](edge-benchmark.md) | Methodology + runbook for benchmarking inference on edge hardware. |

## Project summary

| Document | Covers |
|---|---|
| [`final-report.md`](final-report.md) | What was built, the headline results, and the honest limitations. |
| [`deliverables/`](deliverables/) | Project deliverable documents (design document, components overview, model comparison, presentation outlines, handover email, meeting reports). See [`deliverables/README.md`](deliverables/README.md). |

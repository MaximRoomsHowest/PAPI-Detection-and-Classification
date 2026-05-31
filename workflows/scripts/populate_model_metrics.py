"""Read an Ultralytics training run and emit real metrics — no more hand-typed tables.

Ultralytics writes one `results.csv` row per epoch plus an `args.yaml`. The model
registry (`models/MODELS.md`), the alternative-model comparison
(`docs/deliverables/06-model-comparison.md`) and the backend `/api/model`
provenance endpoint all need the *same* numbers out of those two files. Until now
they were `<!-- TEAM -->` placeholders even though the data was sitting in the repo.

This script parses a run directory and produces either:
  * a JSON model-card (``--json`` / ``--write-model-card``) consumed by the backend
    ``model_registry`` service, or
  * a Markdown table row (``--markdown``) for pasting into MODELS.md / 06-model-comparison.

Honesty guardrails (the project's design principle — no invented numbers):
  * ``results.csv`` holds **validation-split box (B) detection** metrics, not the
    held-out test split and not per-class. The card is labelled accordingly and the
    per-state F1 cells are left for the team to fill from the evaluation notebook.
  * The "best" epoch is chosen by Ultralytics' fitness (0.1*mAP50 + 0.9*mAP50-95),
    which is what ``best.pt`` is saved against — and the final epoch is reported too.

Usage:
    python workflows/scripts/populate_model_metrics.py models/runs/detect/yolo26s-fulldata-1280
    python workflows/scripts/populate_model_metrics.py <run_dir> --write-model-card models/serving/model_card.json
    python workflows/scripts/populate_model_metrics.py <run_dir> --markdown
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is a declared dependency
    yaml = None

# Ultralytics fitness weighting — what `best.pt` is selected against.
_FITNESS_W_MAP50 = 0.1
_FITNESS_W_MAP5095 = 0.9

_METRIC_COLUMNS = {
    "precision": "metrics/precision(B)",
    "recall": "metrics/recall(B)",
    "map50": "metrics/mAP50(B)",
    "map50_95": "metrics/mAP50-95(B)",
}

_VAL_METRIC_NOTE = (
    "Validation-split box (B) detection metrics from results.csv - not the held-out "
    "test regime and not per-class (red/white). Fill per-state F1 from the evaluation "
    "notebook (04_*)."
)


def _to_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_epoch_rows(results_csv: Path) -> list[dict[str, Any]]:
    """Parse results.csv into a list of per-epoch dicts (numeric where possible)."""
    with results_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows: list[dict[str, Any]] = []
        for raw in reader:
            row = {key.strip(): (value.strip() if value is not None else "") for key, value in raw.items()}
            rows.append(row)
    if not rows:
        raise ValueError(f"No data rows in {results_csv}")
    return rows


def _metrics_for_row(row: dict[str, Any]) -> dict[str, float | None]:
    return {name: _to_float(row.get(column, "")) for name, column in _METRIC_COLUMNS.items()}


def _fitness(metrics: dict[str, float | None]) -> float:
    map50 = metrics.get("map50") or 0.0
    map5095 = metrics.get("map50_95") or 0.0
    return _FITNESS_W_MAP50 * map50 + _FITNESS_W_MAP5095 * map5095


def select_epochs(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (best_fitness_epoch, final_epoch) records with their metrics attached."""
    enriched = []
    for row in rows:
        metrics = _metrics_for_row(row)
        epoch = _to_float(row.get("epoch", ""))
        enriched.append(
            {
                "epoch": int(epoch) if epoch is not None else None,
                "metrics": metrics,
                "fitness": _fitness(metrics),
            }
        )
    best = max(enriched, key=lambda item: item["fitness"])
    final = enriched[-1]
    return best, final


def read_args(run_dir: Path) -> dict[str, Any]:
    args_path = run_dir / "args.yaml"
    if not args_path.is_file() or yaml is None:
        return {}
    try:
        return yaml.safe_load(args_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}


def _round_metrics(metrics: dict[str, float | None]) -> dict[str, float | None]:
    return {name: (round(value, 4) if value is not None else None) for name, value in metrics.items()}


def build_model_card(
    run_dir: Path, model_id: str | None = None, classes: dict[int, str] | None = None
) -> dict[str, Any]:
    results_csv = run_dir / "results.csv"
    if not results_csv.is_file():
        raise FileNotFoundError(f"results.csv not found in {run_dir}")

    rows = read_epoch_rows(results_csv)
    best, final = select_epochs(rows)
    args = read_args(run_dir)

    card: dict[str, Any] = {
        "model_id": model_id or run_dir.name,
        "training_run": run_dir.name,
        "base_weights": Path(str(args.get("model", ""))).name or None,
        "task": args.get("task"),
        "imgsz": args.get("imgsz"),
        "batch": args.get("batch"),
        "epochs_configured": args.get("epochs"),
        "epochs_trained": final["epoch"],
        "seed": args.get("seed"),
        "deterministic": args.get("deterministic"),
        "split_evaluated": args.get("split", "val"),
        "val_metrics": {
            "selection": "best_fitness_epoch",
            "epoch": best["epoch"],
            **_round_metrics(best["metrics"]),
            "note": _VAL_METRIC_NOTE,
        },
        "final_epoch_metrics": {
            "epoch": final["epoch"],
            **_round_metrics(final["metrics"]),
        },
        "source_results_csv": results_csv.as_posix(),
        "generated_by": "workflows/scripts/populate_model_metrics.py",
    }
    if classes:
        card["classes"] = {str(class_id): str(name) for class_id, name in classes.items()}
    return card


def _read_class_names(run_dir: Path) -> dict[int, str] | None:
    """Best-effort read of the trained model's class names from weights/best.pt.

    Returns None when ultralytics or the weights are unavailable, so the card simply
    omits ``classes`` rather than this otherwise stdlib-only script hard-failing.
    """
    weights = run_dir / "weights" / "best.pt"
    if not weights.is_file():
        return None
    try:
        from ultralytics import YOLO

        names = YOLO(str(weights)).names
    except Exception:  # noqa: BLE001 - any load failure just means "no classes"
        return None
    return {int(k): str(v) for k, v in names.items()} if isinstance(names, dict) else None


def _fmt(value: float | None) -> str:
    return f"{value:.4f}" if isinstance(value, (int, float)) else "—"


def render_markdown(card: dict[str, Any]) -> str:
    best = card["val_metrics"]
    final = card["final_epoch_metrics"]
    lines = [
        f"### {card['model_id']} metrics (auto-filled from results.csv)",
        "",
        f"- Base: `{card['base_weights']}`, imgsz {card['imgsz']}, batch {card['batch']}, "
        f"seed {card['seed']}, trained {card['epochs_trained']}/{card['epochs_configured']} epochs",
        f"- Evaluated on the **{card['split_evaluated']}** split (box detection metrics; not per-class)",
        "",
        "| Selection | Epoch | precision | recall | mAP@0.5 | mAP@0.5:0.95 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        f"| best fitness | {best['epoch']} | {_fmt(best['precision'])} | {_fmt(best['recall'])} "
        f"| {_fmt(best['map50'])} | {_fmt(best['map50_95'])} |",
        f"| final epoch | {final['epoch']} | {_fmt(final['precision'])} | {_fmt(final['recall'])} "
        f"| {_fmt(final['map50'])} | {_fmt(final['map50_95'])} |",
        "",
        f"> {best['note']}",
    ]
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", type=Path, help="Ultralytics run directory containing results.csv + args.yaml")
    parser.add_argument("--model-id", default=None, help="Stable model id (defaults to the run-dir name)")
    parser.add_argument("--json", action="store_true", help="Print the model card as JSON to stdout")
    parser.add_argument("--markdown", action="store_true", help="Print a Markdown metrics fragment to stdout")
    parser.add_argument(
        "--write-model-card",
        type=Path,
        default=None,
        help="Write the model card JSON to this path (e.g. models/serving/model_card.json)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    classes = _read_class_names(args.run_dir)
    card = build_model_card(args.run_dir, model_id=args.model_id, classes=classes)

    if args.write_model_card is not None:
        args.write_model_card.parent.mkdir(parents=True, exist_ok=True)
        args.write_model_card.write_text(json.dumps(card, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote model card -> {args.write_model_card}")

    if args.markdown:
        print(render_markdown(card))
    if args.json or not (args.markdown or args.write_model_card):
        print(json.dumps(card, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

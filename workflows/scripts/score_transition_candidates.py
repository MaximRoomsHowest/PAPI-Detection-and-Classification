"""Score + rank flip-anchored transition candidates (Phase 4) for the Phase 5 review.

Reads ``transition_candidates.csv`` (flip-anchored), scores each via ``papi.transition_scoring``
(offset proximity + colour intermediacy, with suspect-telemetry flags), and writes
``transition_candidates_ranked.csv`` + a tier summary. Labels are never changed here; tiers only
steer how many candidates a human inspects and in what order.

Run::

    .venv/Scripts/python workflows/scripts/score_transition_candidates.py
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from papi.transition_scoring import (
    TIER_AMBIGUOUS,
    TIER_HIGH,
    TIER_LOW,
    TIER_MEDIUM,
    score,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TWIN = REPO_ROOT / "data" / "datasets" / "transition-classification-data"
TIER_RANK = {TIER_HIGH: 0, TIER_MEDIUM: 1, TIER_LOW: 2, TIER_AMBIGUOUS: 3}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def rank(twin: Path) -> dict:
    candidates = _read_csv(twin / "transition_candidates.csv")
    enriched: list[dict[str, str]] = []
    for row in candidates:
        try:
            colour = json.loads(row.get("colour_features") or "{}")
        except json.JSONDecodeError:
            colour = {}
        result = score(
            colour=colour,
            frame_offset=int(row.get("frame_offset") or 0),
            quality_flags=row.get("quality_flags", ""),
            runway=row.get("runway", ""),
        )
        enriched.append({**row, **{k: str(v) for k, v in result.items()}})

    enriched.sort(key=lambda r: (TIER_RANK.get(r["tier"], 9), -float(r["transition_score"])))
    out_path = twin / "transition_candidates_ranked.csv"
    fieldnames = list(enriched[0].keys()) if enriched else []
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(enriched)

    manifest = {
        "total": len(enriched),
        "tiers": dict(Counter(r["tier"] for r in enriched)),
        "by_type": dict(Counter(r["transition_type"] for r in enriched)),
        "review_flagged": sum(1 for r in enriched if r["review_flag"]),
        "review_flag_breakdown": dict(
            Counter(f for r in enriched for f in r["review_flag"].split(";") if f)
        ),
        "ranked_csv": str(out_path),
    }
    (twin / "transition_ranking_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--twin", type=Path, default=DEFAULT_TWIN)
    args = parser.parse_args()
    print(json.dumps(rank(args.twin), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Structured provenance for the serving model.

`/api/model` needs to answer the question an Intersoft safety reviewer actually
asks: *which trained run is serving, and how accurate is it?* The training metrics
live in the run's `results.csv`; `workflows/scripts/populate_model_metrics.py`
distils them into a `model_card.json` placed next to the serving weights. This
module reads that card (provenance + val metrics) and computes the on-disk SHA-256
so the deployed checkpoint can be verified against a release.

If the card is absent (e.g. a local dev checkout with bare weights) every field is
simply ``None`` — the endpoint degrades gracefully rather than failing.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_HASH_CHUNK_BYTES = 1024 * 1024
_MODEL_CARD_FILENAME = "model_card.json"


@lru_cache(maxsize=8)
def _sha256_cached(path_str: str, mtime_ns: int, size: int) -> str:
    """SHA-256 keyed on (path, mtime, size) so it recomputes only when the file changes."""
    digest = hashlib.sha256()
    with open(path_str, "rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_sha256(path: Path) -> str | None:
    """Return the SHA-256 hex digest of ``path`` (None if it is not a readable file)."""
    if not path.is_file():
        return None
    try:
        stat = path.stat()
        return _sha256_cached(str(path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None


def load_model_card(model_path: Path) -> dict[str, Any] | None:
    """Load the ``model_card.json`` sitting next to the serving weights, or None."""
    card_path = model_path.parent / _MODEL_CARD_FILENAME
    if not card_path.is_file():
        return None
    try:
        data = json.loads(card_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None

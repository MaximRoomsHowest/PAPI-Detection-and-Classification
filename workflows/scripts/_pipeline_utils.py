"""Shared helpers for the offline PAPI pipeline scripts.

These scripts run as standalone files with ``workflows/scripts`` on ``sys.path``
(``python workflows/scripts/<name>.py``), so sibling modules import each other by
bare module name. This module collects the small helpers that were previously
copy-pasted across several of those scripts: YAML loading, reading YOLO labels out
of a CVAT annotations zip, and normalizing one-based CVAT class IDs to the
zero-based detector convention.

Behavior is intentionally identical to the original inline copies; this is a
mechanical de-duplication, not a logic change.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import yaml


def load_yaml(path: Path) -> dict:
    """Load a YAML document from ``path`` as a dict."""
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def read_label_zip(zip_path: Path) -> dict[str, str]:
    """Read non-empty ``labels/train/*.txt`` entries from a CVAT YOLO zip.

    Returns a mapping of label stem -> newline-terminated label text. Empty label
    files are skipped so they never overwrite a populated label from an earlier zip.
    """
    labels: dict[str, str] = {}
    with zipfile.ZipFile(zip_path) as archive:
        for name in archive.namelist():
            path = Path(name)
            if len(path.parts) < 3 or path.parts[-3:-1] != ("labels", "train") or path.suffix != ".txt":
                continue
            text = archive.read(name).decode("utf-8")
            if text.strip():
                labels[path.stem] = text if text.endswith("\n") else f"{text}\n"
    return labels


def source_uses_zero_based_labels(label_path: Path, class_names: dict[int, str]) -> bool:
    """Decide whether a correction export already uses zero-based detector IDs.

    Older CVAT exports used one-based task IDs and need remapping; newer normalized
    YOLO exports use zero-based IDs and are kept as-is. The sibling ``data.yaml`` (two
    directories above ``labels/train``) disambiguates by class-name order. When no
    usable ``data.yaml`` is present, default to zero-based (kept as-is).
    """
    source_dir = label_path.parents[2]
    data_yaml = source_dir / "data.yaml"
    if data_yaml.exists():
        data = yaml.safe_load(data_yaml.read_text(encoding="utf-8")) or {}
        names = data.get("names", {})
        if isinstance(names, dict):
            normalized = {int(key): value for key, value in names.items()}
            if normalized.get(0) == class_names[0]:
                return True
            if normalized.get(1) == class_names[0]:
                return False
    return True


def remap_label_text(
    label_path: Path,
    class_names: dict[int, str],
    remap: dict[int, int],
) -> str:
    """Normalize a YOLO label file's class IDs to the zero-based detector convention.

    Reads ``label_path`` and returns newline-terminated label text. Zero-based exports
    are validated against ``class_names`` and kept verbatim; one-based exports have
    their leading class ID rewritten via ``remap``. Any class ID that is neither a
    known zero-based ID nor a known remap key raises ``ValueError`` (e.g. a transition
    row, which is no longer a detector class).

    Returns an empty string when the file has no label rows. The caller is responsible
    for skipping files that do not exist if that distinction matters.
    """
    rows = [line.split() for line in label_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        return ""

    already_zero_based = source_uses_zero_based_labels(label_path, class_names)

    lines: list[str] = []
    for parts in rows:
        class_id = int(parts[0])
        if already_zero_based:
            if class_id not in class_names:
                raise ValueError(f"Unsupported detector class {class_id} in {label_path}")
            lines.append(" ".join(parts))
        elif class_id in remap:
            lines.append(" ".join([str(remap[class_id]), *parts[1:]]))
        else:
            raise ValueError(f"Unsupported detector class {class_id} in {label_path}")
    return "\n".join(lines) + ("\n" if lines else "")

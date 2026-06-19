"""Build a self-contained training bundle for the "prepare + run externally" path.

The operator downloads a zip (dataset + manifest + README) and runs the existing
trainer on their own GPU, then re-imports the resulting best.pt via model upload.
The colour-safe augmentation matches workflows/scripts/train_transition_model.py
so the external run reproduces the project's training regime.
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

from app.config import Settings

# The run name is interpolated into a shell command the operator copy-pastes, so
# it must be restricted to a safe charset (also exactly what Ultralytics accepts
# for a run-directory name) — never trust the raw, user-supplied dataset name.
_UNSAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_run_name(name: str) -> str:
    cleaned = _UNSAFE_NAME_RE.sub("-", name).strip("-._")
    return cleaned[:64] or "papi-train"

# Colour-safe augmentation (hue/sat jitter would swap red<->white<->transition).
COLOUR_SAFE_AUG: dict[str, float] = {
    "hsv_h": 0.0,
    "hsv_s": 0.0,
    "hsv_v": 0.2,
    "fliplr": 0.5,
    "flipud": 0.0,
    "degrees": 0.0,
    "translate": 0.1,
    "scale": 0.5,
    "mosaic": 0.0,
}


def build_command(
    *, base: str, epochs: int, imgsz: int, batch: int, oversample: int, name: str, class_count: int
) -> str:
    """Build the copy-paste trainer command, routed by the dataset's class count.

    A 3-class dataset (red/white/transition) trains with the transition trainer
    (``--combined <dir>``, supports ``--oversample``); a 2-class dataset (red/white)
    trains with the detector trainer (``--data <data.yaml>``, no oversample). Wiring
    every dataset to the transition trainer mislabels 2-class detector bundles, since
    that trainer overrides the data.yaml names with the 3-class map (audit 2026-06-19).

    epochs/imgsz/batch/oversample are ints (schema-validated); ``name`` is the only
    free-text field, so it is hardened before it lands in the shell string.
    """
    safe_name = _safe_run_name(name)
    common = (
        f"--base models/base/{base} "
        f"--epochs {epochs} --imgsz {imgsz} --batch {batch} --device 0 "
        f"--name {safe_name}"
    )
    if class_count >= 3:
        return (
            "python workflows/scripts/train_transition_model.py "
            "--combined ./dataset "
            f"{common} --oversample {oversample}"
        )
    return (
        "python workflows/scripts/train_detector_model.py "
        "--data ./dataset/data.yaml "
        f"{common}"
    )


def _readme(manifest: dict[str, Any]) -> str:
    return (
        "PAPI external training bundle\n"
        "=============================\n\n"
        "1. Unzip this archive. The labelled YOLO dataset is under ./dataset.\n"
        "2. From the PAPI repo root (with the .venv active and a CUDA GPU), run:\n\n"
        f"   {manifest['command']}\n\n"
        "   (The dataset path in the command is relative to the unzipped ./dataset folder.)\n\n"
        "3. When training finishes, upload the resulting best.pt back into the app\n"
        "   via the Models page (Upload model) to make it selectable for inference.\n\n"
        "Augmentation is colour-safe by design (hsv_h=0, hsv_s=0): hue/saturation\n"
        "jitter would swap red<->white<->transition labels.\n\n"
        f"Manifest:\n{json.dumps(manifest, indent=2)}\n"
    )


def _portable_data_yaml(text: str) -> str:
    """Rewrite a dataset data.yaml's ``path:`` to a portable relative value.

    On disk, datasets.write_data_yaml stamps ``path: <server-absolute datasets_dir>``,
    which does not exist on the operator's machine — so the bundled
    ``--data ./dataset/data.yaml`` (the 2-class detector branch) would resolve no
    images and training would fail. ``path: .`` makes Ultralytics resolve train/val/test
    relative to the yaml's own directory (the unzipped ./dataset folder) wherever it
    lands (audit 2026-06-19; the transition trainer sidesteps this by rebuilding the
    yaml from its --combined dir at runtime, so this is also harmless there).
    """
    out: list[str] = []
    replaced = False
    for line in text.splitlines():
        if not replaced and line.lstrip().startswith("path:"):
            out.append("path: .")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.insert(0, "path: .")
    return "\n".join(out) + "\n"


def build_training_bundle(settings: Settings, root: Path, job_id: str, manifest: dict[str, Any]) -> Path:
    out_dir = settings.jobs_dir / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = out_dir / "bundle.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if rel.parts and rel.parts[0] == "_raw":
                continue
            if "_staging" in rel.parts or CANDIDATES_DIR_NAME in rel.parts:
                continue
            rel_posix = rel.as_posix()
            if rel_posix == "data.yaml":
                # Make the bundled yaml portable so it resolves against the unzipped
                # ./dataset folder, not the backend's absolute datasets_dir (audit).
                archive.writestr(f"dataset/{rel_posix}", _portable_data_yaml(path.read_text(encoding="utf-8")))
                continue
            archive.write(path, f"dataset/{rel_posix}")
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        archive.writestr("README.txt", _readme(manifest))
    return bundle


CANDIDATES_DIR_NAME = "_candidates"

"""Build a self-contained training bundle for the "prepare + run externally" path.

The operator downloads a zip (dataset + manifest + README) and runs the existing
trainer on their own GPU, then re-imports the resulting best.pt via model upload.
The colour-safe augmentation matches workflows/scripts/train_transition_model.py
so the external run reproduces the project's training regime.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from app.config import Settings

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


def build_command(*, base: str, epochs: int, imgsz: int, batch: int, oversample: int, name: str) -> str:
    return (
        "python workflows/scripts/train_transition_model.py "
        "--combined ./dataset "
        f"--base models/base/{base} "
        f"--epochs {epochs} --imgsz {imgsz} --batch {batch} --device 0 "
        f"--oversample {oversample} --name {name}"
    )


def _readme(manifest: dict[str, Any]) -> str:
    return (
        "PAPI external training bundle\n"
        "=============================\n\n"
        "1. Unzip this archive. The labelled YOLO dataset is under ./dataset.\n"
        "2. From the PAPI repo root (with the .venv active and a CUDA GPU), run:\n\n"
        f"   {manifest['command']}\n\n"
        "   (Point --combined at the unzipped ./dataset directory.)\n\n"
        "3. When training finishes, upload the resulting best.pt back into the app\n"
        "   via the Models page (Upload model) to make it selectable for inference.\n\n"
        "Augmentation is colour-safe by design (hsv_h=0, hsv_s=0): hue/saturation\n"
        "jitter would swap red<->white<->transition labels.\n\n"
        f"Manifest:\n{json.dumps(manifest, indent=2)}\n"
    )


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
            archive.write(path, f"dataset/{rel.as_posix()}")
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        archive.writestr("README.txt", _readme(manifest))
    return bundle


CANDIDATES_DIR_NAME = "_candidates"

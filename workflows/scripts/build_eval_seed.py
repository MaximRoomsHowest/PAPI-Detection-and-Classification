"""Curate the small, committed, per-role evaluation seeds under ``data/eval/``.

The real labeled data (``data/datasets/``) is gitignored and made of ~20 MP DJI
frames (3.6 MB each), so it can't ship with the app. This script carves a tiny,
flight-separated, downscaled (1280 px longest edge) subset per role so the backend
can seed a built-in default evaluation set on startup:

* ``builtin-detector-redwhite`` — 2-class (red/white), from a held-out red/white
  test-view flight; used to score the 2-class serving detectors.
* ``builtin-transition-3class`` — 3-class (red/white/transition), from a daytime
  flight that is in NEITHER the transition model's train nor test split (verified),
  so the eval is leak-free; used to score the 3-class transition model.

YOLO labels are normalized (class cx cy w h), so downscaling the image does not
change them — labels are copied verbatim. Selection is deterministic (no RNG):
transition frames are taken first (they are rare), then the rest are spread evenly
across the flight to cover the descent's red->white sweep.

Run::

    .venv/Scripts/python workflows/scripts/build_eval_seed.py
"""

from __future__ import annotations

import shutil
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "data" / "datasets" / "transition-classification-data"
OUT_ROOT = REPO_ROOT / "data" / "eval"
MAX_EDGE = 1280
JPEG_QUALITY = 85
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

TARGETS = [
    {
        "id": "builtin-detector-redwhite",
        "src": SRC_ROOT / "redwhite_test_view" / "DJI_202604281946_014_1000",
        "n": 18,
        "n_classes": 2,
        "class_names": {0: "papi_light_red", 1: "papi_light_white"},
        "source_flight": "DJI_202604281946_014_1000 (redwhite_test_view, daytime red/white test view)",
    },
    {
        "id": "builtin-transition-3class",
        "src": SRC_ROOT / "daytime" / "DJI_202604291357_034_600day2up",
        "n": 24,
        "n_classes": 3,
        "class_names": {0: "papi_light_red", 1: "papi_light_white", 2: "papi_light_transition"},
        "source_flight": "DJI_202604291357_034_600day2up (daytime, held out of the transition train AND test splits)",
    },
]


def _classes_in(label_path: Path) -> set[int]:
    classes: set[int] = set()
    for line in label_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            classes.add(int(float(line.split()[0])))
    return classes


def _annotated_pairs(src: Path) -> list[tuple[Path, Path, set[int]]]:
    img_dir, lab_dir = src / "images", src / "labels"
    pairs: list[tuple[Path, Path, set[int]]] = []
    for img in sorted(img_dir.iterdir()):
        if img.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        lab = lab_dir / f"{img.stem}.txt"
        if not lab.exists() or not lab.read_text(encoding="utf-8").strip():
            continue  # eval needs annotated frames
        pairs.append((img, lab, _classes_in(lab)))
    return pairs


def _select(pairs: list[tuple[Path, Path, set[int]]], n: int, n_classes: int):
    """Deterministic pick: rare transition frames first, then an even temporal spread."""
    chosen: list[tuple[Path, Path, set[int]]] = []
    taken: set[Path] = set()
    if n_classes >= 3:
        transition = [p for p in pairs if 2 in p[2]]
        for p in transition[: max(1, n // 3)]:
            chosen.append(p)
            taken.add(p[0])
    rest = [p for p in pairs if p[0] not in taken]
    need = n - len(chosen)
    if need > 0 and rest:
        stride = max(1, len(rest) // need)
        for i in range(0, len(rest), stride):
            chosen.append(rest[i])
            if len(chosen) >= n:
                break
    # Stable order by filename for a reproducible, browsable seed.
    return sorted(chosen, key=lambda p: p[0].name)[:n]


def _resize_save(src_img: Path, dst_img: Path) -> None:
    from PIL import Image

    with Image.open(src_img) as im:
        im = im.convert("RGB")
        w, h = im.size
        scale = min(1.0, MAX_EDGE / max(w, h))
        if scale < 1.0:
            im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
        dst_img.parent.mkdir(parents=True, exist_ok=True)
        im.save(dst_img, "JPEG", quality=JPEG_QUALITY)


def _write_readme(out: Path, target: dict, n: int, boxes: Counter, frames: Counter) -> None:
    names = target["class_names"]
    lines = [
        f"# {target['id']}",
        "",
        f"Built-in PAPI evaluation set ({target['n_classes']}-class). Seeded into the",
        "datasets table on backend startup and used as the default evaluation set for",
        f"{'detector' if target['n_classes'] == 2 else 'transition'}-role models.",
        "",
        f"- **Source flight:** {target['source_flight']}",
        f"- **Frames:** {n} (downscaled to {MAX_EDGE}px longest edge, JPEG q{JPEG_QUALITY})",
        "- **Split:** all frames are the `test` split (held-out evaluation only).",
        "- **Provenance:** flight-separated from training data, so metrics are leak-free.",
        "",
        "## Class coverage",
        "",
        "| id | class | boxes | frames |",
        "| -- | ----- | ----- | ------ |",
    ]
    for cid in sorted(names):
        lines.append(f"| {cid} | {names[cid]} | {boxes.get(cid, 0)} | {frames.get(cid, 0)} |")
    lines.append("")
    lines.append("Regenerate with `python workflows/scripts/build_eval_seed.py`.")
    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build(target: dict) -> None:
    src = target["src"]
    if not src.is_dir():
        print(f"  SKIP {target['id']}: source missing ({src})")
        return
    out = OUT_ROOT / target["id"]
    if out.exists():
        shutil.rmtree(out)
    (out / "images").mkdir(parents=True)
    (out / "labels").mkdir(parents=True)

    chosen = _select(_annotated_pairs(src), target["n"], target["n_classes"])
    boxes: Counter = Counter()
    frames: Counter = Counter()
    for img, lab, classes in chosen:
        _resize_save(img, out / "images" / f"{img.stem}.jpg")
        shutil.copyfile(lab, out / "labels" / f"{img.stem}.txt")
        for line in lab.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                boxes[int(float(line.split()[0]))] += 1
        for c in classes:
            frames[c] += 1

    _write_readme(out, target, len(chosen), boxes, frames)
    print(
        f"  {target['id']}: {len(chosen)} frames -> {out.relative_to(REPO_ROOT)} | "
        f"boxes={dict(sorted(boxes.items()))} frames_with_class={dict(sorted(frames.items()))}"
    )


def main() -> int:
    print(f"Building eval seeds under {OUT_ROOT.relative_to(REPO_ROOT)} ...")
    for target in TARGETS:
        build(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

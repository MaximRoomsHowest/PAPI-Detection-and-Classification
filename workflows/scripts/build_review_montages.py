"""Render per-flip review montages for manual transition verification (Phase 5).

The review unit is the flip event: one red<->white flip seeds ~4 window candidates that share a
verdict. For a stratified sample of flips this renders a strip of the tracked lamp's crop across
[flip-3 .. flip+3], annotated with frame index, original label state, and whether the frame is a
seeded transition box -- so a reviewer can see the colour actually change (or not). Strips are
tiled onto review pages (PNG). Also writes review_sample_flips.csv (the sampled flips + context)
to drive the HTML review app and the verification log.

Run::

    .venv/Scripts/python workflows/scripts/build_review_montages.py --max-flips 36
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TWIN = REPO_ROOT / "data" / "datasets" / "transition-classification-data"
REGIMES = ("daytime", "nighttime")
CONTEXT = 3          # frames to show each side of the flip boundary
CROP_PX = 54         # source region (px) around the lamp centre
UPSCALE = 3          # crop display zoom
CELL = CROP_PX * UPSCALE


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _video_dir(twin: Path, source_id: str) -> Path | None:
    for regime in REGIMES:
        d = twin / regime / source_id
        if d.is_dir():
            return d
    return None


def _flip_key(row: dict) -> tuple[str, str, str]:
    return (row["source_id"], row["track_id"], row["flip_frame"])


def select_flips(ranked: list[dict], max_flips: int) -> list[dict]:
    """One record per flip, stratified across tier/type/runway/flag for coverage."""
    flips: dict[tuple, dict] = {}
    for r in ranked:
        key = _flip_key(r)
        f = flips.setdefault(key, {
            "source_id": r["source_id"], "track_id": r["track_id"], "lamp_position": r["lamp_position"],
            "flip_frame": int(r["flip_frame"]), "transition_type": r["transition_type"],
            "runway": r["runway"], "frames": [], "tiers": [], "flags": set(),
        })
        f["frames"].append(int(r["frame_number"]))
        f["tiers"].append(r["tier"])
        if r["review_flag"]:
            f["flags"].update(r["review_flag"].split(";"))
    records = list(flips.values())

    def stratum(f: dict) -> tuple:
        flag = next(iter(sorted(f["flags"])), "clean")
        return (f["runway"], f["transition_type"], flag)

    by_stratum: dict[tuple, list[dict]] = defaultdict(list)
    for f in sorted(records, key=lambda x: (x["source_id"], x["track_id"], x["flip_frame"])):
        by_stratum[stratum(f)].append(f)
    # round-robin across strata until we hit max_flips
    selected: list[dict] = []
    idx = 0
    strata = sorted(by_stratum)
    while len(selected) < max_flips and any(by_stratum.values()):
        s = strata[idx % len(strata)]
        if by_stratum[s]:
            selected.append(by_stratum[s].pop(0))
        idx += 1
        if idx > len(strata) * (max_flips + 2):
            break
    return selected[:max_flips]


def render_strip(video_dir: Path, track_state: dict, seeded: set[int], flip: dict) -> np.ndarray | None:
    meta = {int(r["sequence_index"]): r["file"] for r in _read_csv(video_dir / "metadata.csv")}
    lo, hi = flip["flip_frame"] - CONTEXT, flip["flip_frame"] + CONTEXT + 1
    cells = []
    for fr in range(lo, hi + 1):
        box = track_state.get((flip["track_id"], fr))
        cell = np.full((CELL, CELL, 3), 40, np.uint8)
        if box and fr in meta:
            img = cv2.imread(str(video_dir / "images" / meta[fr]))
            if img is not None:
                H, W = img.shape[:2]
                cxp, cyp = int(float(box["cx"]) * W), int(float(box["cy"]) * H)
                x1, y1 = max(0, cxp - CROP_PX // 2), max(0, cyp - CROP_PX // 2)
                crop = img[y1:y1 + CROP_PX, x1:x1 + CROP_PX]
                if crop.size:
                    cell = cv2.resize(crop, (CELL, CELL), interpolation=cv2.INTER_NEAREST)
            state = box["state"]
            border = (0, 165, 255) if fr in seeded else ((40, 40, 220) if state == "red" else (220, 220, 220))
            cv2.rectangle(cell, (0, 0), (CELL - 1, CELL - 1), border, 3)
            cv2.putText(cell, f"{fr}:{state[0]}{'*' if fr in seeded else ''}", (3, 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 0), 1, cv2.LINE_AA)
        cells.append(cell)
    strip = cv2.hconcat(cells)
    header = np.full((26, strip.shape[1], 3), 25, np.uint8)
    flags = ",".join(sorted(flip["flags"])) or "clean"
    txt = (f"{flip['source_id'][:24]} {flip['track_id']} {flip['transition_type']} "
           f"rwy{flip['runway']} [{flags}]  (*=seeded transition)")
    cv2.putText(header, txt, (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 220, 180), 1, cv2.LINE_AA)
    return cv2.vconcat([header, strip])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--twin", type=Path, default=DEFAULT_TWIN)
    parser.add_argument("--max-flips", type=int, default=36)
    parser.add_argument("--per-page", type=int, default=6)
    args = parser.parse_args()

    ranked = _read_csv(args.twin / "transition_candidates_ranked.csv")
    flips = select_flips(ranked, args.max_flips)

    out_dir = args.twin / "review_assets"
    out_dir.mkdir(parents=True, exist_ok=True)

    # cache tracks state per video
    track_cache: dict[str, dict] = {}
    strips: list[tuple[dict, np.ndarray]] = []
    for flip in flips:
        vd = _video_dir(args.twin, flip["source_id"])
        if vd is None:
            continue
        if flip["source_id"] not in track_cache:
            ts = {(r["track_id"], int(r["frame_index"])): r for r in _read_csv(vd / "tracks.csv")}
            track_cache[flip["source_id"]] = ts
        seeded = set(flip["frames"])
        strip = render_strip(vd, track_cache[flip["source_id"]], seeded, flip)
        if strip is not None:
            strips.append((flip, strip))

    # tile strips onto pages
    width = max((s.shape[1] for _, s in strips), default=0)
    pages = 0
    for p in range(0, len(strips), args.per_page):
        chunk = [s for _, s in strips[p:p + args.per_page]]
        chunk = [cv2.copyMakeBorder(s, 0, 8, 0, width - s.shape[1], cv2.BORDER_CONSTANT, value=(15, 15, 15)) for s in chunk]
        page = cv2.vconcat(chunk)
        cv2.imwrite(str(out_dir / f"review_page_{pages + 1:02d}.png"), page)
        pages += 1

    sample_rows = []
    for i, (flip, _s) in enumerate(strips):
        sample_rows.append({
            "review_id": f"flip_{i + 1:03d}", "source_id": flip["source_id"], "track_id": flip["track_id"],
            "lamp_position": flip["lamp_position"], "flip_frame": flip["flip_frame"],
            "transition_type": flip["transition_type"], "runway": flip["runway"],
            "frames": ";".join(str(f) for f in sorted(flip["frames"])),
            "flags": ",".join(sorted(flip["flags"])) or "clean",
            "page": i // args.per_page + 1,
        })
    with (out_dir / "review_sample_flips.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(sample_rows[0].keys()))
        writer.writeheader()
        writer.writerows(sample_rows)

    print(json.dumps({"flips_sampled": len(strips), "pages": pages, "out_dir": str(out_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

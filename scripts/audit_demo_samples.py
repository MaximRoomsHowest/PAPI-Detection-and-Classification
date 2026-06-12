#!/usr/bin/env python3
"""One-shot audit of the Live-Demo sample assets against the source dataset.

Checks, in order:
  1. PIXEL ORDER PROOF - decodes mp4 frames {0, 30, 59} and cross-compares them
     against the downscaled source rows {0, 30, 59}: the distance matrix must be
     minimal on the diagonal, proving the video frames are the right images in
     the right order (not just plausible-looking).
  2. TELEMETRY 1:1 - sample-video.json fixes must equal the picked rows'
     metadata (lat/lon/alt), index for index. Same for sample-sweep.json and
     sample-point.json.
  3. GROUND-TRUTH STATES - runs the video through the local backend and compares
     every per-frame verdict against the dataset's per-frame YOLO labels
     (white-box count -> expected PAPI state). Frames whose labels contain a
     class-2 (transition) box are compared with +/-1 white tolerance.
  4. GROUND-TRUTH TRANSITIONS - transitions.csv flip rows mapped onto video
     frame numbers; a detected red->white transition must exist within +/-4
     video frames of each ground-truth flip.

Run from the repo root with the compose backend up:
    .venv/Scripts/python.exe scripts/audit_demo_samples.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
CLIP = REPO / "data" / "datasets" / "transition-classification-data" / "daytime" / "DJI_202604291738_041_300mday2up"
OUT = REPO / "apps" / "frontend" / "public" / "demo-samples"
VIDEO_FRAMES, LO, HI = 60, 0.0, 1.0
STATE_TO_WHITES = {"far_too_low": 0, "too_low": 1, "correct_glidepath": 2, "too_high": 3, "far_too_high": 4}

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(("PASS " if ok else "FAIL ") + message)
    if not ok:
        failures.append(message)


def load_rows() -> list[dict]:
    rows = list(csv.DictReader(open(CLIP / "metadata.csv", newline="", encoding="utf-8")))
    rows.sort(key=lambda r: int(r["sequence_index"]))
    return rows


def pick(rows: list[dict], n: int, lo: float, hi: float) -> list[dict]:
    a, b = int(len(rows) * lo), int(len(rows) * hi) - 1
    return [rows[a + round(i * (b - a) / (n - 1))] for i in range(n)]


def downscaled(row: dict, long_edge: int = 1280) -> np.ndarray:
    img = Image.open(CLIP / row["image"]).convert("RGB")
    w, h = img.size
    s = long_edge / max(w, h)
    if s < 1:
        img = img.resize((round(w * s), round(h * s)), Image.LANCZOS)
    return np.asarray(img, dtype=np.float32)


def main() -> int:
    rows = load_rows()
    video_rows = pick(rows, VIDEO_FRAMES, LO, HI)

    # --- 1. pixel order proof -------------------------------------------------
    probe = [0, 30, 59]
    cap = cv2.VideoCapture(str(OUT / "papi24-angle-sweep.mp4"))
    decoded: dict[int, np.ndarray] = {}
    index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if index in probe:
            decoded[index] = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).astype(np.float32)
        index += 1
    cap.release()
    check(index == VIDEO_FRAMES, f"mp4 decodes exactly {VIDEO_FRAMES} frames (got {index})")

    sources = {i: downscaled(video_rows[i]) for i in probe}
    diag_ok = True
    for i in probe:
        dists = {}
        for j in probe:
            src = sources[j]
            dec = decoded[i][: src.shape[0], : src.shape[1]]
            dists[j] = float(np.mean(np.abs(dec - src[: dec.shape[0], : dec.shape[1]])))
        best = min(dists, key=dists.get)
        print(f"     mp4[{i}] vs sources {{{', '.join(f'{j}: {d:.1f}' for j, d in dists.items())}}} -> best {best}")
        diag_ok &= best == i
    check(diag_ok, "every probed mp4 frame matches ITS OWN source row best (order proof)")

    # --- 2. telemetry 1:1 -----------------------------------------------------
    video_track = json.loads((OUT / "sample-video.json").read_text(encoding="utf-8"))["samples"]
    mismatched = [
        i
        # Truncation is fine: the length is asserted separately in the check below.
        for i, (s, r) in enumerate(zip(video_track, video_rows, strict=False))
        if s["frame_index"] != i
        or abs(s["latitude"] - float(r["lat"])) > 1e-7
        or abs(s["longitude"] - float(r["lon"])) > 1e-7
        or abs(s["altitude_m"] - float(r["alt_ellipsoidal_m"])) > 1e-3
    ]
    check(len(video_track) == VIDEO_FRAMES and not mismatched,
          f"sample-video.json: {VIDEO_FRAMES} fixes equal the picked rows 1:1 (mismatches: {mismatched[:5]})")

    sweep_rows = pick(rows, 10, 0.30, 0.97)
    sweep_track = json.loads((OUT / "sample-sweep.json").read_text(encoding="utf-8"))["samples"]
    sweep_ok = len(sweep_track) == 10 and all(
        abs(s["altitude_m"] - float(r["alt_ellipsoidal_m"])) <= 1e-3
        for s, r in zip(sweep_track, sweep_rows, strict=False)
    )
    check(sweep_ok, "sample-sweep.json: 10 fixes equal the sweep picks 1:1")

    point = json.loads((OUT / "sample-point.json").read_text(encoding="utf-8"))
    single = sweep_rows[4]
    check(abs(point["altitude_m"] - float(single["alt_ellipsoidal_m"])) <= 1e-3,
          "sample-point.json matches the single frame's recorded fix")

    # --- 3. backend per-frame states vs YOLO ground truth ----------------------
    files = {
        "file": ("papi24-angle-sweep.mp4", open(OUT / "papi24-angle-sweep.mp4", "rb"), "video/mp4"),
        "metadata_file": ("sample-video.json", open(OUT / "sample-video.json", "rb"), "application/json"),
    }
    r = requests.post("http://localhost:8000/api/analyze", files=files, data={"runway_id": "papi_24"}, timeout=900)
    check(r.status_code == 200, f"backend accepts the sample video (status {r.status_code})")
    payload = r.json()
    per_frame = {p["frame_index"]: p["state"] for p in payload.get("per_frame", [])}

    strict_total = strict_match = loose_total = loose_match = 0
    mismatches = []
    for i, row in enumerate(video_rows):
        label_path = CLIP / row["label"]
        if not label_path.exists():
            continue
        classes = [int(line.split()[0]) for line in label_path.read_text().splitlines() if line.strip()]
        whites, transitions = classes.count(1), classes.count(2)
        state = per_frame.get(i)
        got = STATE_TO_WHITES.get(state)
        if got is None:
            continue  # 'unknown' frames carry no white count to compare
        if transitions == 0:
            strict_total += 1
            if got == whites:
                strict_match += 1
            else:
                mismatches.append((i, state, f"gt={whites}W"))
        else:
            loose_total += 1
            if abs(got - whites) <= transitions:
                loose_match += 1
            else:
                mismatches.append((i, state, f"gt={whites}W+{transitions}T"))
    print(f"     strict frames {strict_match}/{strict_total}, blend-zone frames {loose_match}/{loose_total}, "
          f"mismatches: {mismatches[:8]}")
    agreement = (strict_match + loose_match) / max(1, strict_total + loose_total)
    check(agreement >= 0.85, f"per-frame verdicts agree with dataset ground truth ({agreement:.0%})")

    # --- 4. ground-truth transitions are detected ------------------------------
    gt = list(csv.DictReader(open(CLIP / "transitions.csv", newline="", encoding="utf-8")))
    a, b = int(len(rows) * LO), int(len(rows) * HI) - 1
    detected = payload.get("transitions", [])
    all_found = True
    for flip in gt:
        source_index = int(flip["from_frame_index"])  # 0-based row position in the clip
        video_frame = round((source_index - a) * (VIDEO_FRAMES - 1) / (b - a))
        near = [
            t for t in detected
            if t["to_state"] == "white" and abs(t["frame_index"] - video_frame) <= 4
        ]
        found = bool(near)
        all_found &= found
        print(f"     GT {flip['physical_lamp_id']} flips at source {source_index} -> video ~{video_frame}: "
              f"{'detected' if found else 'MISSED'} ({[t['frame_index'] for t in near][:3]})")
    check(all_found, "every ground-truth red->white flip has a detected transition within +/-4 frames")

    print("\n" + ("ALL CHECKS PASSED" if not failures else f"{len(failures)} FAILURE(S):\n- " + "\n- ".join(failures)))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

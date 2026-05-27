"""Visual PAPI lamp detection for CVAT pre-annotation.

This is intentionally simple and deterministic: find bright red/white blobs, then keep the
four candidates that form the most PAPI-like horizontal row.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage


@dataclass(frozen=True)
class VisualLampDetection:
    state: str
    bbox_xyxy_px: tuple[float, float, float, float]


@dataclass(frozen=True)
class _Candidate:
    cx: float
    cy: float
    x1: int
    y1: int
    x2: int
    y2: int
    area: int
    red_pixels: int
    white_pixels: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def state(self) -> str:
        if self.red_pixels >= 8 and self.white_pixels >= 8:
            ratio = self.red_pixels / max(1, self.white_pixels)
            if 0.45 <= ratio <= 1.8:
                return "transition"
        if self.red_pixels >= max(8, int(0.35 * self.white_pixels)):
            return "red"
        return "white"

    def padded_bbox(self, image_width: int, image_height: int) -> tuple[float, float, float, float]:
        pad = max(2.0, 0.15 * max(self.width, self.height))
        return (
            max(0.0, self.x1 - pad),
            max(0.0, self.y1 - pad),
            min(float(image_width - 1), self.x2 + pad),
            min(float(image_height - 1), self.y2 + pad),
        )


def detect_visual_lamps(image_path: Path) -> list[VisualLampDetection]:
    """Detect visible PAPI lamp blobs and classify their observed color state."""
    image = Image.open(image_path).convert("RGB")
    arr = np.asarray(image)
    image_height, image_width = arr.shape[:2]
    candidates = _find_candidates(arr)
    row = _select_papi_row(candidates)
    return [
        VisualLampDetection(c.state, c.padded_bbox(image_width, image_height))
        for c in sorted(row, key=lambda candidate: candidate.cx)
    ]


def _find_candidates(arr: np.ndarray) -> list[_Candidate]:
    red_mask, white_mask = _lamp_masks(arr)
    mask = red_mask | white_mask
    labels, _ = ndimage.label(mask)
    objects = ndimage.find_objects(labels)
    max_channel = arr.max(axis=2).astype(np.float32)
    image_height, image_width = arr.shape[:2]
    candidates: list[_Candidate] = []

    for label_id, slices in enumerate(objects, start=1):
        if slices is None:
            continue
        y_slice, x_slice = slices
        component = labels[slices] == label_id
        area = int(component.sum())
        width = x_slice.stop - x_slice.start
        height = y_slice.stop - y_slice.start

        if area < 5 or area > 8_000 or width > 220 or height > 220:
            continue
        if y_slice.start < image_height * 0.20:
            continue
        if x_slice.start <= 1 or x_slice.stop >= image_width - 1:
            continue

        yy, xx = np.nonzero(component)
        yy = yy + y_slice.start
        xx = xx + x_slice.start
        weights = max_channel[yy, xx]
        weight_sum = float(weights.sum())
        if weight_sum <= 0.0:
            continue

        candidates.append(
            _Candidate(
                cx=float((xx * weights).sum() / weight_sum),
                cy=float((yy * weights).sum() / weight_sum),
                x1=int(x_slice.start),
                y1=int(y_slice.start),
                x2=int(x_slice.stop),
                y2=int(y_slice.stop),
                area=area,
                red_pixels=int(red_mask[yy, xx].sum()),
                white_pixels=int(white_mask[yy, xx].sum()),
            )
        )

    return candidates


def _lamp_masks(arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rgb = arr.astype(np.float32)
    red = rgb[:, :, 0]
    green = rgb[:, :, 1]
    blue = rgb[:, :, 2]
    spread = rgb.max(axis=2) - rgb.min(axis=2)

    red_mask = (red > 150) & (red > green * 1.45) & (red > blue * 1.45)
    white_mask = (red > 190) & (green > 160) & (blue > 110) & (spread < 90)
    return red_mask, white_mask


def _select_papi_row(candidates: list[_Candidate]) -> list[_Candidate]:
    if len(candidates) <= 4:
        return sorted(candidates, key=lambda candidate: candidate.cx)

    # Keep the search bounded on noisy zoom images while preserving strong lamp candidates.
    shortlist = sorted(candidates, key=lambda c: c.area, reverse=True)[:50]
    best_group: tuple[_Candidate, ...] | None = None
    best_score = float("inf")

    for anchor in shortlist:
        row_candidates = [
            c for c in shortlist
            if abs(c.cy - anchor.cy) <= max(45.0, 0.03 * anchor.cy)
        ]
        row_candidates = sorted(row_candidates, key=lambda c: c.area, reverse=True)[:16]
        if len(row_candidates) < 4:
            continue

        for group in combinations(row_candidates, 4):
            ordered = tuple(sorted(group, key=lambda c: c.cx))
            xs = np.array([c.cx for c in ordered], dtype=float)
            ys = np.array([c.cy for c in ordered], dtype=float)
            spacings = np.diff(xs)
            if np.any(spacings <= 0):
                continue
            median_spacing = float(np.median(spacings))
            if median_spacing < 15.0:
                continue
            if float(np.ptp(ys)) > max(60.0, 0.35 * median_spacing):
                continue

            spacing_cv = float(np.std(spacings) / max(1.0, median_spacing))
            if spacing_cv > 0.45:
                continue

            areas = np.array([c.area for c in ordered], dtype=float)
            area_cv = float(np.std(areas) / max(1.0, float(np.mean(areas))))
            score = float(np.ptp(ys)) * 3.0 + spacing_cv * 250.0 + area_cv * 25.0
            # Prefer larger bright components when row geometry is otherwise similar.
            score -= float(np.mean(areas)) * 0.02
            if score < best_score:
                best_score = score
                best_group = ordered

    if best_group is None:
        return []
    return list(best_group)

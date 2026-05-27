"""Per-lamp tracking annotations and transition extraction for sequence datasets."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment

from .geometry import resolve_papi_for_frame
from .projection import ProjectionConvention, project_papi_lights

TRACK_FIELDNAMES = [
    "video_id",
    "frame_index",
    "file",
    "label",
    "track_id",
    "physical_lamp_id",
    "class_id",
    "state",
    "cx",
    "cy",
    "w",
    "h",
    "cx_px",
    "cy_px",
    "assignment_method",
    "assignment_distance_px",
    "quality_flags",
]

TRANSITION_FIELDNAMES = [
    "video_id",
    "track_id",
    "physical_lamp_id",
    "from_frame_index",
    "to_frame_index",
    "from_file",
    "to_file",
    "from_state",
    "to_state",
    "transition_type",
]

CLASS_ID_TO_STATE = {
    0: "red",
    1: "white",
}


@dataclass(frozen=True)
class YoloDetection:
    """One normalized YOLO detection row with pixel center convenience fields."""

    row_index: int
    class_id: int
    cx: float
    cy: float
    w: float
    h: float
    image_width: int
    image_height: int

    @property
    def state(self) -> str:
        return CLASS_ID_TO_STATE[self.class_id]

    @property
    def cx_px(self) -> float:
        return self.cx * self.image_width

    @property
    def cy_px(self) -> float:
        return self.cy * self.image_height


def read_yolo_detections(label_path: Path, image_width: int, image_height: int) -> list[YoloDetection]:
    """Read a same-stem YOLO label file as normalized red/white lamp detections."""
    detections: list[YoloDetection] = []
    if not label_path.exists():
        raise FileNotFoundError(label_path)

    for row_index, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 5:
            raise ValueError(f"{label_path}:{row_index}: expected 5 YOLO fields, got {len(parts)}")
        class_id = int(parts[0])
        if class_id not in CLASS_ID_TO_STATE:
            raise ValueError(f"{label_path}:{row_index}: invalid detector class {class_id}")
        cx, cy, w, h = (float(value) for value in parts[1:])
        if any(value < 0.0 or value > 1.0 for value in (cx, cy, w, h)):
            raise ValueError(f"{label_path}:{row_index}: normalized YOLO coordinate outside [0, 1]")
        detections.append(
            YoloDetection(
                row_index=row_index,
                class_id=class_id,
                cx=cx,
                cy=cy,
                w=w,
                h=h,
                image_width=image_width,
                image_height=image_height,
            )
        )
    return detections


def assign_frame_tracks(
    *,
    video_id: str,
    image_row: dict[str, Any],
    label_rel: str,
    detections: list[YoloDetection],
    airport_config: dict[str, Any] | None = None,
    projection_convention: ProjectionConvention | None = None,
    projection_max_distance_px: float = 300.0,
) -> list[dict[str, str]]:
    """Assign stable lamp track IDs for one frame.

    Projection assignment is preferred because it preserves physical lamp identity even when the
    row appears mirrored in the image. If projection is unavailable or implausible, the fallback
    assigns left-to-right identity within the frame and marks that in `assignment_method`.
    """
    if not detections:
        return []

    assignments = _assign_by_projection(
        image_row=image_row,
        detections=detections,
        airport_config=airport_config,
        projection_convention=projection_convention,
        projection_max_distance_px=projection_max_distance_px,
    )
    if assignments is None:
        assignments = _assign_by_left_to_right(detections)

    frame_index = str(int(image_row["sequence_index"]))
    file_name = str(image_row["file"])
    rows: list[dict[str, str]] = []
    for detection, physical_lamp_id, method, distance_px, quality_flags in assignments:
        is_physical_lamp = 1 <= physical_lamp_id <= 4
        rows.append(
            {
                "video_id": video_id,
                "frame_index": frame_index,
                "file": file_name,
                "label": label_rel,
                "track_id": f"lamp_{physical_lamp_id}" if is_physical_lamp else f"extra_{physical_lamp_id}",
                "physical_lamp_id": str(physical_lamp_id) if is_physical_lamp else "",
                "class_id": str(detection.class_id),
                "state": detection.state,
                "cx": f"{detection.cx:.6f}",
                "cy": f"{detection.cy:.6f}",
                "w": f"{detection.w:.6f}",
                "h": f"{detection.h:.6f}",
                "cx_px": f"{detection.cx_px:.3f}",
                "cy_px": f"{detection.cy_px:.3f}",
                "assignment_method": method,
                "assignment_distance_px": "" if distance_px is None else f"{distance_px:.3f}",
                "quality_flags": ";".join(quality_flags),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            int(row["frame_index"]),
            99 if row["physical_lamp_id"] == "" else int(row["physical_lamp_id"]),
            row["track_id"],
        ),
    )


def detect_transitions(track_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Detect red/white switches per stable lamp track.

    A transition is emitted only between consecutive observed frames for the same track. This
    avoids inventing a switch across a missing-label gap.
    """
    by_track: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in track_rows:
        by_track[(row["video_id"], row["track_id"])].append(row)

    transitions: list[dict[str, str]] = []
    for (video_id, track_id), rows in sorted(by_track.items()):
        ordered = sorted(rows, key=lambda row: int(row["frame_index"]))
        for previous, current in zip(ordered, ordered[1:], strict=False):
            previous_frame = int(previous["frame_index"])
            current_frame = int(current["frame_index"])
            if current_frame != previous_frame + 1:
                continue
            if previous["state"] == current["state"]:
                continue
            if {previous["state"], current["state"]} != {"red", "white"}:
                continue
            transition_type = f"{previous['state']}_to_{current['state']}"
            transitions.append(
                {
                    "video_id": video_id,
                    "track_id": track_id,
                    "physical_lamp_id": previous["physical_lamp_id"],
                    "from_frame_index": previous["frame_index"],
                    "to_frame_index": current["frame_index"],
                    "from_file": previous["file"],
                    "to_file": current["file"],
                    "from_state": previous["state"],
                    "to_state": current["state"],
                    "transition_type": transition_type,
                }
            )
    return transitions


def summarize_tracking(track_rows: list[dict[str, str]], transition_rows: list[dict[str, str]]) -> dict[str, Any]:
    """Return compact counts for a video or full dataset tracking manifest."""
    return {
        "track_rows": len(track_rows),
        "transitions": len(transition_rows),
        "transitions_by_type": dict(Counter(row["transition_type"] for row in transition_rows)),
        "assignment_methods": dict(Counter(row["assignment_method"] for row in track_rows)),
        "quality_flags": dict(
            Counter(
                flag
                for row in track_rows
                for flag in row["quality_flags"].split(";")
                if flag
            )
        ),
    }


def _assign_by_projection(
    *,
    image_row: dict[str, Any],
    detections: list[YoloDetection],
    airport_config: dict[str, Any] | None,
    projection_convention: ProjectionConvention | None,
    projection_max_distance_px: float,
) -> list[tuple[YoloDetection, int, str, float | None, list[str]]] | None:
    if airport_config is None or projection_convention is None:
        return None
    if str(image_row.get("camera")) != "WideCamera":
        return None

    _, papi_config = resolve_papi_for_frame(image_row, airport_config)
    camera_config = airport_config["cameras"]["wide"]
    projections = project_papi_lights(
        image_row,
        papi_config,
        camera_config,
        projection_convention,
    )
    projected_points = [
        (lamp_id, float(u), float(v))
        for lamp_id, (u, v, behind, _in_frame) in projections.items()
        if not behind and u is not None and v is not None
    ]
    if len(projected_points) < len(detections):
        return None

    costs = np.array(
        [
            [np.hypot(det.cx_px - u, det.cy_px - v) for _, u, v in projected_points]
            for det in detections
        ],
        dtype=float,
    )
    det_indices, projection_indices = linear_sum_assignment(costs)
    max_cost = float(
        max(
            costs[det_i, proj_i]
            for det_i, proj_i in zip(det_indices, projection_indices, strict=True)
        )
    )
    if max_cost > projection_max_distance_px:
        return None

    assignments: list[tuple[YoloDetection, int, str, float | None, list[str]]] = []
    for det_i, proj_i in zip(det_indices, projection_indices, strict=True):
        lamp_id = projected_points[proj_i][0]
        distance_px = float(costs[det_i, proj_i])
        flags: list[str] = []
        if distance_px > projection_max_distance_px * 0.75:
            flags.append("high_projection_distance")
        assignments.append((detections[det_i], lamp_id, "projection", distance_px, flags))
    return assignments


def _assign_by_left_to_right(
    detections: list[YoloDetection],
) -> list[tuple[YoloDetection, int, str, float | None, list[str]]]:
    ordered = sorted(detections, key=lambda detection: detection.cx_px)
    assignments: list[tuple[YoloDetection, int, str, float | None, list[str]]] = []
    for index, detection in enumerate(ordered, 1):
        lamp_id = index
        flags = ["fallback_left_to_right"]
        if len(detections) > 4:
            flags.append("over_four_detections")
        assignments.append((detection, lamp_id, "left_to_right", None, flags))
    return assignments

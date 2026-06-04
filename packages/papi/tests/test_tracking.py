"""Tracking and temporal transition tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from papi.geometry import resolve_papi_for_frame
from papi.projection import DEFAULT_CONVENTION, project_papi_lights
from papi.tracking import (
    YoloDetection,
    assign_frame_tracks,
    detect_transitions,
    read_yolo_detections,
    summarize_tracking,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]

# A WideCamera pose ~500 m down the runway-06 approach that keeps all four PAPI lamps in
# front of the camera (verified against the projection code). yaw=0 (north) with the camera
# SSW of the lamps places them as a near-horizontal row on the right of the frame.
_APPROACH_ROW = {
    "sequence_index": 1,
    "file": "frame_0001.JPG",
    "camera": "WideCamera",
    "lat": 47.665022,
    "lon": 9.500579,
    "alt_ellipsoidal_m": 496.37,
    "gimbal_yaw_deg": 0.0,
    "gimbal_pitch_deg": -4.5,
    "gimbal_roll_deg": 0.0,
}


def _airport_cfg() -> dict:
    """Load the real EDNY airport config (runway geometry + wide-camera intrinsics)."""
    return yaml.safe_load((_REPO_ROOT / "configs" / "papi_edny.yaml").read_text(encoding="utf-8"))


def _det(row_index: int, class_id: int, cx: float) -> YoloDetection:
    return YoloDetection(
        row_index=row_index,
        class_id=class_id,
        cx=cx,
        cy=0.5,
        w=0.1,
        h=0.1,
        image_width=1000,
        image_height=500,
    )


def _row(frame_index: int, state: str, track_id: str = "lamp_1") -> dict[str, str]:
    class_id = "0" if state == "red" else "1"
    return {
        "video_id": "video_a",
        "frame_index": str(frame_index),
        "file": f"frame_{frame_index:04d}.JPG",
        "label": f"labels/frame_{frame_index:04d}.txt",
        "track_id": track_id,
        "physical_lamp_id": track_id.removeprefix("lamp_"),
        "class_id": class_id,
        "state": state,
        "cx": "0.5",
        "cy": "0.5",
        "w": "0.1",
        "h": "0.1",
        "cx_px": "500.0",
        "cy_px": "250.0",
        "assignment_method": "left_to_right",
        "assignment_distance_px": "",
        "quality_flags": "fallback_left_to_right",
    }


def test_left_to_right_assignment_is_stable_with_no_projection_config():
    rows = assign_frame_tracks(
        video_id="video_a",
        image_row={"sequence_index": 1, "file": "frame_0001.JPG"},
        label_rel="labels/frame_0001.txt",
        detections=[_det(1, 1, 0.4), _det(2, 0, 0.2), _det(3, 1, 0.8), _det(4, 0, 0.6)],
    )

    assert [row["track_id"] for row in rows] == ["lamp_1", "lamp_2", "lamp_3", "lamp_4"]
    assert [row["state"] for row in rows] == ["red", "white", "red", "white"]
    assert {row["assignment_method"] for row in rows} == {"left_to_right"}


def test_detect_transitions_reports_both_directions():
    transitions = detect_transitions(
        [
            _row(1, "white", "lamp_1"),
            _row(2, "red", "lamp_1"),
            _row(3, "white", "lamp_1"),
        ]
    )

    assert [row["transition_type"] for row in transitions] == ["white_to_red", "red_to_white"]


def test_detect_transitions_ignores_state_change_across_missing_frame_gap():
    transitions = detect_transitions(
        [
            _row(1, "white", "lamp_1"),
            _row(3, "red", "lamp_1"),
        ]
    )

    assert transitions == []


def test_read_yolo_detections_parses_valid_label(tmp_path):
    """A well-formed YOLO label reads back as red/white detections with normalized
    coords and pixel-center convenience fields, preserving 1-based row order."""
    label = tmp_path / "frame_0001.txt"
    label.write_text(
        "0 0.150000 0.500000 0.100000 0.200000\n1 0.750000 0.500000 0.100000 0.200000\n",
        encoding="utf-8",
    )
    detections = read_yolo_detections(label, image_width=1000, image_height=500)
    assert [d.state for d in detections] == ["red", "white"]
    assert [d.row_index for d in detections] == [1, 2]
    assert detections[0].cx == pytest.approx(0.15)
    assert detections[1].cx_px == pytest.approx(750.0)  # 0.75 * 1000


def test_read_yolo_detections_skips_blank_lines(tmp_path):
    label = tmp_path / "frame.txt"
    label.write_text("0 0.5 0.5 0.1 0.1\n\n   \n1 0.6 0.5 0.1 0.1\n", encoding="utf-8")
    assert len(read_yolo_detections(label, 1000, 500)) == 2


def test_read_yolo_detections_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_yolo_detections(tmp_path / "does_not_exist.txt", 1000, 500)


@pytest.mark.parametrize(
    "line, match",
    [
        pytest.param("0 0.5 0.5 0.1", "expected 5 YOLO fields", id="too-few-fields"),
        pytest.param("0 0.5 0.5 0.1 0.1 0.1", "expected 5 YOLO fields", id="too-many-fields"),
        pytest.param("7 0.5 0.5 0.1 0.1", "invalid detector class", id="bad-class-id"),
        pytest.param("0 1.5 0.5 0.1 0.1", r"outside \[0, 1\]", id="coord-above-one"),
        pytest.param("1 0.5 -0.1 0.1 0.1", r"outside \[0, 1\]", id="coord-below-zero"),
    ],
)
def test_read_yolo_detections_rejects_malformed_rows(tmp_path, line, match):
    """Malformed rows raise ValueError rather than silently corrupting downstream data."""
    label = tmp_path / "bad.txt"
    label.write_text(line + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        read_yolo_detections(label, image_width=1000, image_height=500)


def test_assign_frame_tracks_prefers_projection_over_left_to_right():
    """With a real airport config + projection convention and a WideCamera frame, lamps are
    assigned by PROJECTION so physical identity is preserved -- even though the detections are
    fed in reversed order and lamp_1 is actually the RIGHT-most lamp on screen."""
    airport_config = _airport_cfg()
    camera_config = airport_config["cameras"]["wide"]
    width = int(camera_config["width"])
    height = int(camera_config["height"])

    _, papi_config = resolve_papi_for_frame(_APPROACH_ROW, airport_config)
    projections = project_papi_lights(_APPROACH_ROW, papi_config, camera_config, DEFAULT_CONVENTION)
    assert all(
        (not behind) and u is not None and in_frame
        for (u, _v, behind, in_frame) in projections.values()
    ), "fixture must keep all four lamps in front of and within the camera frame"

    # One detection placed exactly at each lamp's projected pixel, fed in REVERSED physical
    # order. A left-to-right fallback would label them by screen-x; only projection recovers
    # that the right-most detection is physically lamp_1.
    detections = [
        YoloDetection(
            row_index=row_index,
            class_id=1,
            cx=projections[lamp_id][0] / width,
            cy=projections[lamp_id][1] / height,
            w=0.02,
            h=0.02,
            image_width=width,
            image_height=height,
        )
        for row_index, lamp_id in enumerate([4, 3, 2, 1], start=1)
    ]

    rows = assign_frame_tracks(
        video_id="video_proj",
        image_row=_APPROACH_ROW,
        label_rel="labels/frame_0001.txt",
        detections=detections,
        airport_config=airport_config,
        projection_convention=DEFAULT_CONVENTION,
    )

    assert {row["assignment_method"] for row in rows} == {"projection"}
    assert [row["track_id"] for row in rows] == ["lamp_1", "lamp_2", "lamp_3", "lamp_4"]
    by_lamp = {row["track_id"]: row for row in rows}
    for lamp_id in (1, 2, 3, 4):
        assert float(by_lamp[f"lamp_{lamp_id}"]["cx_px"]) == pytest.approx(
            projections[lamp_id][0], abs=1.0
        )
    # The clincher: lamp_1 is to the RIGHT of lamp_4 on screen -- the opposite of what a
    # left-to-right labelling would produce, so this can only be projection assignment.
    assert float(by_lamp["lamp_1"]["cx_px"]) > float(by_lamp["lamp_4"]["cx_px"])


def test_assign_frame_tracks_falls_back_when_detections_far_from_projection():
    """When detections are nowhere near the projected lamp positions (every match cost beyond
    projection_max_distance_px), projection is rejected and the frame falls back to
    left-to-right so no detection is silently dropped."""
    airport_config = _airport_cfg()
    camera_config = airport_config["cameras"]["wide"]
    width = int(camera_config["width"])
    height = int(camera_config["height"])

    # Lamps project to the right side of the frame; cluster the detections far to the lower
    # left so the cheapest possible assignment still exceeds the 300 px threshold.
    detections = [
        YoloDetection(
            row_index=i + 1,
            class_id=1,
            cx=0.02 + i * 0.01,
            cy=0.9,
            w=0.02,
            h=0.02,
            image_width=width,
            image_height=height,
        )
        for i in range(4)
    ]

    rows = assign_frame_tracks(
        video_id="video_fallback",
        image_row=_APPROACH_ROW,
        label_rel="labels/frame_0001.txt",
        detections=detections,
        airport_config=airport_config,
        projection_convention=DEFAULT_CONVENTION,
    )

    assert {row["assignment_method"] for row in rows} == {"left_to_right"}
    assert [row["track_id"] for row in rows] == ["lamp_1", "lamp_2", "lamp_3", "lamp_4"]
    assert all("fallback_left_to_right" in row["quality_flags"] for row in rows)


def test_summarize_tracking_counts_rows_methods_flags_and_transitions():
    track_rows = [
        _row(1, "white", "lamp_1"),
        _row(2, "red", "lamp_1"),
        _row(1, "white", "lamp_2"),
    ]
    transition_rows = detect_transitions([_row(1, "white", "lamp_1"), _row(2, "red", "lamp_1")])
    summary = summarize_tracking(track_rows, transition_rows)
    assert summary["track_rows"] == 3
    assert summary["transitions"] == 1
    assert summary["transitions_by_type"] == {"white_to_red": 1}
    assert summary["assignment_methods"] == {"left_to_right": 3}
    assert summary["quality_flags"] == {"fallback_left_to_right": 3}

"""Tracking and temporal transition tests."""

from __future__ import annotations

from papi.tracking import YoloDetection, assign_frame_tracks, detect_transitions


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

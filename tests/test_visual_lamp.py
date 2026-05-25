from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from papi.visual_lamp import detect_visual_lamps


def test_detect_visual_lamps_finds_row_and_observed_states(tmp_path: Path) -> None:
    image_path = tmp_path / "papi.jpg"
    image = Image.new("RGB", (600, 300), (40, 70, 35))
    draw = ImageDraw.Draw(image)

    centers = [(180, 170), (260, 171), (340, 169), (420, 170)]
    colors = [(240, 20, 20), (255, 235, 210), (255, 230, 205), (230, 20, 20)]
    for center, color in zip(centers, colors, strict=True):
        x, y = center
        draw.ellipse((x - 7, y - 6, x + 7, y + 6), fill=color)

    # Add a bright distractor that is not part of the evenly spaced PAPI row.
    draw.rectangle((40, 120, 70, 130), fill=(255, 240, 220))
    image.save(image_path)

    detections = detect_visual_lamps(image_path)

    assert [d.state for d in detections] == ["red", "white", "white", "red"]
    assert len(detections) == 4
    for detection, (expected_x, expected_y) in zip(detections, centers, strict=True):
        x1, y1, x2, y2 = detection.bbox_xyxy_px
        assert x1 <= expected_x <= x2
        assert y1 <= expected_y <= y2
        assert x2 - x1 < 25
        assert y2 - y1 < 25

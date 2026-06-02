"""Lazy OpenCV import shared by the inference modules.

OpenCV is an optional-at-import heavy dependency: importing it eagerly at module
load would make the whole service unimportable (and the test suite uncollectable)
on a box without the wheel. Every code path that needs cv2 calls ``require_cv2()``
so the missing-dependency error is raised only when inference is actually attempted.
"""

from typing import Any


def require_cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is not installed. Run `pip install -r requirements.txt`.") from exc
    return cv2

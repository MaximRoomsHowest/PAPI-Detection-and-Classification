"""Inference service package.

Split out of the former single ``app/services/inference.py`` module into cohesive
units (codec/video-writer, overlay drawing, per-lamp aggregation, cv2 loader, and
the ``InferenceService`` facade). The public surface is unchanged: importers and
tests keep doing ``from app.services.inference import InferenceService`` /
``get_inference_service``. The leaf helpers are re-exported too for convenience.
"""

from app.services.inference.aggregation import aggregate_video_lamps
from app.services.inference.cv2_loader import require_cv2
from app.services.inference.overlay import LAMP_COLORS, draw_overlay
from app.services.inference.service import InferenceService, get_inference_service
from app.services.inference.video_writer import open_video_writer

__all__ = [
    "InferenceService",
    "get_inference_service",
    "aggregate_video_lamps",
    "draw_overlay",
    "LAMP_COLORS",
    "open_video_writer",
    "require_cv2",
]

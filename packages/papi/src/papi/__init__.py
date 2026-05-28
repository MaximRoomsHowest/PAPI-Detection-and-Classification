"""PAPI auto-labelling + geometry library.

Pure, dependency-light helpers shared by the offline pipeline (workflows /
notebooks) and the analysis backend: WGS84 geometry, per-lamp white/red/transition
state, the four-lamp -> global glidepath decoder, and YOLO label I/O.

The curated re-exports below are the stable public surface (audit IMP-ML-1) — import
``from papi import derive_global_state`` rather than reaching into submodules.
"""

from __future__ import annotations

from .geometry import (
    elevation_angle_deg,
    geodetic_to_enu,
    horizontal_distance_m,
    resolve_papi_for_frame,
)
from .global_state import GLOBAL_STATES, derive_global_state
from .io import (
    LAMP_STATE_CLASS_IDS,
    LAMP_STATE_CLASS_NAMES,
    write_yolo_label,
    write_yolo_labels,
)
from .lamp_state import compute_lamp_state

__version__ = "0.1.0"
__author__ = "Howest Industry-Project Team"
__url__ = "https://github.com/MaximRoomsHowest/PAPI-Detection-and-Classification"

__all__ = [
    "__version__",
    "__author__",
    "__url__",
    # global glidepath decoding
    "GLOBAL_STATES",
    "derive_global_state",
    # per-lamp state from geometry
    "compute_lamp_state",
    # WGS84 geometry
    "resolve_papi_for_frame",
    "elevation_angle_deg",
    "geodetic_to_enu",
    "horizontal_distance_m",
    # YOLO label I/O
    "LAMP_STATE_CLASS_NAMES",
    "LAMP_STATE_CLASS_IDS",
    "write_yolo_label",
    "write_yolo_labels",
]

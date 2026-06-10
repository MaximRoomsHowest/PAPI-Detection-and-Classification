"""Rank flip-anchored transition candidates to prioritize manual review.

Every candidate already sits next to an authoritative red<->white flip, so the ranking job is
narrower than open candidate mining: decide which window frames are most clearly the visible
blend (vs a near-stable window edge), and surface suspect cases for human eyes. Signals:

* **offset proximity** (weight 0.6) — frames at the flip boundary (offset 0, +/-1) are the most
  likely genuinely-intermediate; window edges (+/-2) are often already near-stable.
* **colour intermediacy** (weight 0.4) — red+white coexistence and amber/yellow presence inside
  the lamp. A weak per-frame signal (small overexposed lamps read amber even when stable), so it
  refines rather than drives the rank, and never sets a label.

`review_flag` records why a candidate warrants human attention: ``elev_discontinuity`` (bad
telemetry at the flip), ``fallback_identity`` (left-to-right lamp id, less trustworthy), ``rwy06``
(FAA default angles, commissioned set-angles pending). Of these, ONLY ``elev_discontinuity`` also
forces the ``ambiguous`` tier regardless of score; the other two annotate without changing the tier.
"""

from __future__ import annotations

import math

TIER_HIGH = "high_confidence_transition_candidate"
TIER_MEDIUM = "medium_confidence_transition_candidate"
TIER_LOW = "low_confidence_transition_candidate"
TIER_AMBIGUOUS = "ambiguous"

W_OFFSET, W_COLOUR = 0.6, 0.4


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _finite(value: object) -> float:
    """Coerce a colour-feature stat to a finite float; NaN/inf/garbage -> 0.0.

    Python's min/max NaN-poison ``_clamp``: ``_clamp(nan)`` returns 1.0, so a NaN
    ratio smuggled in via a JSON round-trip (``allow_nan=True``) would silently score
    as MAXIMAL intermediacy and rank HIGH (audit LS-5). Treat non-finite as absent.
    """
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return result if math.isfinite(result) else 0.0


def offset_proximity(frame_offset: int) -> float:
    """1.0 at the flip boundary, decaying ~0.18 per frame away."""
    return _clamp(1.0 - 0.18 * abs(frame_offset))


def colour_intermediacy(cf: dict) -> float:
    """Red+white coexistence and amber presence; 0 when colour is unavailable."""
    if not cf or cf.get("n_px", 0) < 4:
        return 0.0
    amber = _finite(cf.get("orange_amber_ratio", 0.0)) + _finite(cf.get("yellow_ratio", 0.0))
    mix = 2.0 * min(_finite(cf.get("red_ratio", 0.0)), _finite(cf.get("white_ratio", 0.0)))
    return _clamp(0.6 * mix + 0.4 * min(amber, 0.6))


# Thresholds for calling a crop a *clearly stable* colour (vs an amber blend). The orange/amber
# band IS the transition signal, so a crop is only "red"/"white" when a pure colour dominates the
# lit pixels -- never merely because some red or white is present.
RED_RATIO_MIN = 0.45  # pure-red pixels must be a real share of the crop
RED_DOMINANCE_MIN = 0.65  # ...and dominate the warm (red+amber+yellow) pixels
WHITE_RATIO_MIN = 0.30
WHITE_VAL_MIN = 175.0  # OpenCV value channel: a stable white lamp is bright


def classify_lamp_colour(cf: dict) -> str:
    """Stable-colour verdict for a lamp crop from ``colour_features`` stats.

    Returns ``"red"`` / ``"white"`` when the crop is a *clearly stable* colour (so it is NOT a
    transition and should keep its red/white label), ``"intermediate"`` for an amber/blended crop
    (the genuine transition signal), or ``"unknown"`` when too few lit pixels to judge. Amber-aware
    by construction: ranking by red-as-a-share-of-warm separates a pure-red graze from a red->white
    blend without hand-tuned per-ratio cutoffs. Used by both the label gate (apply_verification) and
    the manual-review triage so the audit numbers and the fix cannot drift apart.
    """
    if not cf or cf.get("n_px", 0) < 16:
        return "unknown"
    red = _finite(cf.get("red_ratio", 0.0))
    amber = _finite(cf.get("orange_amber_ratio", 0.0))
    yellow = _finite(cf.get("yellow_ratio", 0.0))
    white = _finite(cf.get("white_ratio", 0.0))
    val = _finite(cf.get("val_mean", 0.0))
    warm = red + amber + yellow
    if warm < 0.15 and white < 0.15:
        return "unknown"  # crop not clearly lit -> let other signals decide
    red_dominance = red / warm if warm > 0 else 0.0
    if red >= RED_RATIO_MIN and red_dominance >= RED_DOMINANCE_MIN and white <= 0.20:
        return "red"
    if white >= WHITE_RATIO_MIN and val >= WHITE_VAL_MIN and red <= 0.10 and amber <= 0.30:
        return "white"
    return "intermediate"


def review_flag(quality_flags: str, runway: str) -> str:
    flags = []
    if "elev_discontinuity" in quality_flags:
        flags.append("elev_discontinuity")
    if "fallback_left_to_right" in quality_flags:
        flags.append("fallback_identity")
    if runway == "06":
        flags.append("rwy06_faa_default")
    return ";".join(flags)


def tier(score_value: float, frame_offset: int, suspect: bool) -> str:
    if suspect:
        return TIER_AMBIGUOUS
    if score_value >= 0.70 and abs(frame_offset) <= 1:
        return TIER_HIGH
    if score_value >= 0.50:
        return TIER_MEDIUM
    if score_value >= 0.30:
        return TIER_LOW
    return TIER_AMBIGUOUS


def score(*, colour: dict, frame_offset: int, quality_flags: str, runway: str) -> dict:
    prox = offset_proximity(frame_offset)
    col = colour_intermediacy(colour)
    value = round(W_OFFSET * prox + W_COLOUR * col, 4)
    flag = review_flag(quality_flags, runway)
    suspect = "elev_discontinuity" in flag
    return {
        "transition_score": value,
        "score_offset": round(prox, 3),
        "score_colour": round(col, 3),
        "colour_verdict": classify_lamp_colour(colour),
        "tier": tier(value, frame_offset, suspect),
        "review_flag": flag,
    }

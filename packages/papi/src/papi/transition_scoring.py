"""Rank flip-anchored transition candidates to prioritize manual review.

Every candidate already sits next to an authoritative red<->white flip, so the ranking job is
narrower than open candidate mining: decide which window frames are most clearly the visible
blend (vs a near-stable window edge), and surface suspect cases for human eyes. Signals:

* **offset proximity** (weight 0.6) — frames at the flip boundary (offset 0, +/-1) are the most
  likely genuinely-intermediate; window edges (+/-2) are often already near-stable.
* **colour intermediacy** (weight 0.4) — red+white coexistence and amber/yellow presence inside
  the lamp. A weak per-frame signal (small overexposed lamps read amber even when stable), so it
  refines rather than drives the rank, and never sets a label.

`review_flag` forces human attention regardless of score: ``elev_discontinuity`` (bad telemetry
at the flip), ``fallback_identity`` (left-to-right lamp id, less trustworthy), ``rwy06`` (FAA
default angles, commissioned set-angles pending).
"""

from __future__ import annotations

TIER_HIGH = "high_confidence_transition_candidate"
TIER_MEDIUM = "medium_confidence_transition_candidate"
TIER_LOW = "low_confidence_transition_candidate"
TIER_AMBIGUOUS = "ambiguous"

W_OFFSET, W_COLOUR = 0.6, 0.4


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def offset_proximity(frame_offset: int) -> float:
    """1.0 at the flip boundary, decaying ~0.18 per frame away."""
    return _clamp(1.0 - 0.18 * abs(frame_offset))


def colour_intermediacy(cf: dict) -> float:
    """Red+white coexistence and amber presence; 0 when colour is unavailable."""
    if not cf or cf.get("n_px", 0) < 4:
        return 0.0
    amber = float(cf.get("orange_amber_ratio", 0.0)) + float(cf.get("yellow_ratio", 0.0))
    mix = 2.0 * min(float(cf.get("red_ratio", 0.0)), float(cf.get("white_ratio", 0.0)))
    return _clamp(0.6 * mix + 0.4 * min(amber, 0.6))


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
        "tier": tier(value, frame_offset, suspect),
        "review_flag": flag,
    }

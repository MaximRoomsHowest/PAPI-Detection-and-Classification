import pytest
from papi.transition_scoring import (
    TIER_AMBIGUOUS,
    TIER_HIGH,
    TIER_LOW,
    TIER_MEDIUM,
    colour_intermediacy,
    offset_proximity,
    review_flag,
    score,
    tier,
)


def test_offset_proximity_peaks_at_boundary_and_decays_symmetrically():
    assert offset_proximity(0) == 1.0
    assert offset_proximity(1) == pytest.approx(0.82)
    assert offset_proximity(-1) == pytest.approx(0.82)  # symmetric in |offset|
    assert offset_proximity(2) == pytest.approx(0.64)
    # Decays to and clamps at 0 — never negative.
    assert offset_proximity(6) == 0.0


def test_colour_intermediacy_zero_without_enough_pixels():
    assert colour_intermediacy({}) == 0.0
    assert colour_intermediacy({"n_px": 3, "red_ratio": 1.0, "white_ratio": 1.0}) == 0.0


def test_colour_intermediacy_rewards_red_white_coexistence_and_clamps():
    # 0.6 * (2*min(0.5,0.5)) + 0.4*0 = 0.6
    assert colour_intermediacy({"n_px": 100, "red_ratio": 0.5, "white_ratio": 0.5}) == pytest.approx(0.6)
    # Saturated inputs clamp to 1.0.
    saturated = {"n_px": 100, "red_ratio": 1.0, "white_ratio": 1.0, "orange_amber_ratio": 1.0}
    assert colour_intermediacy(saturated) == 1.0


def test_tier_thresholds_and_suspect_override():
    assert tier(0.80, 0, suspect=False) == TIER_HIGH
    assert tier(0.80, 2, suspect=False) == TIER_MEDIUM  # HIGH requires |offset| <= 1
    assert tier(0.60, 0, suspect=False) == TIER_MEDIUM
    assert tier(0.40, 0, suspect=False) == TIER_LOW
    assert tier(0.20, 0, suspect=False) == TIER_AMBIGUOUS
    assert tier(0.95, 0, suspect=True) == TIER_AMBIGUOUS  # suspect forces ambiguous


def test_review_flag_maps_quality_flags_and_runway():
    assert review_flag("elev_discontinuity", "24") == "elev_discontinuity"
    assert review_flag("fallback_left_to_right", "24") == "fallback_identity"
    assert review_flag("", "06") == "rwy06_faa_default"
    assert review_flag("", "24") == ""
    assert (
        review_flag("elev_discontinuity;fallback_left_to_right", "06")
        == "elev_discontinuity;fallback_identity;rwy06_faa_default"
    )


def test_score_integrates_signals_and_only_elev_discontinuity_forces_ambiguous():
    clean = score(colour={}, frame_offset=0, quality_flags="", runway="24")
    assert clean["transition_score"] == pytest.approx(0.6)  # 0.6*1.0 + 0.4*0.0
    assert clean["tier"] == TIER_MEDIUM
    assert clean["review_flag"] == ""

    # rwy06 + fallback are review flags but do NOT force the ambiguous tier...
    flagged = score(colour={}, frame_offset=0, quality_flags="fallback_left_to_right", runway="06")
    assert flagged["tier"] == TIER_MEDIUM
    assert "rwy06_faa_default" in flagged["review_flag"]

    # ...only an elevation discontinuity makes it suspect -> ambiguous.
    suspect = score(colour={}, frame_offset=0, quality_flags="elev_discontinuity", runway="06")
    assert suspect["tier"] == TIER_AMBIGUOUS
    assert "elev_discontinuity" in suspect["review_flag"]

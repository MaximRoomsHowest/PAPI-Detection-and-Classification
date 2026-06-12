import pytest
from papi.transition_scoring import (
    TIER_AMBIGUOUS,
    TIER_HIGH,
    TIER_LOW,
    TIER_MEDIUM,
    classify_lamp_colour,
    colour_intermediacy,
    offset_proximity,
    review_flag,
    score,
    tier,
)


def test_offset_proximity_peaks_at_boundary_pair_and_decays_symmetrically():
    # The flip boundary is the (0, +1) frame pair (offsets measured from from_frame);
    # decay is symmetric in distance from the NEAREST boundary frame (audit LS-3).
    assert offset_proximity(0) == 1.0
    assert offset_proximity(1) == 1.0  # the to-side boundary frame
    assert offset_proximity(-1) == pytest.approx(0.82)
    assert offset_proximity(2) == pytest.approx(0.82)
    assert offset_proximity(-2) == pytest.approx(0.64)
    assert offset_proximity(3) == pytest.approx(0.64)
    # Decays to and clamps at 0 — never negative.
    assert offset_proximity(-6) == 0.0
    assert offset_proximity(7) == 0.0  # eff offset 6, past the decay range


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
    assert tier(0.80, 2, suspect=False) == TIER_HIGH  # +2 is 1 from the (0,+1) boundary pair
    assert tier(0.80, -2, suspect=False) == TIER_MEDIUM  # -2 is 2 from the boundary
    assert tier(0.80, 3, suspect=False) == TIER_MEDIUM
    assert tier(0.60, 0, suspect=False) == TIER_MEDIUM
    assert tier(0.40, 0, suspect=False) == TIER_LOW
    assert tier(0.20, 0, suspect=False) == TIER_AMBIGUOUS
    assert tier(0.95, 0, suspect=True) == TIER_AMBIGUOUS  # suspect forces ambiguous


def test_classify_lamp_colour_unknown_without_enough_signal():
    assert classify_lamp_colour({}) == "unknown"
    assert classify_lamp_colour({"n_px": 8, "red_ratio": 1.0}) == "unknown"  # too few pixels
    # Lit but neither warm nor white -> not classifiable as a stable colour.
    assert classify_lamp_colour({"n_px": 300, "red_ratio": 0.05, "white_ratio": 0.05}) == "unknown"


def test_classify_lamp_colour_flags_stable_red():
    # cand_00031 (frame 189, 3 min from its flip): pure red dominates the warm pixels.
    red = {"n_px": 225, "red_ratio": 0.8667, "orange_amber_ratio": 0.0356,
           "yellow_ratio": 0.0, "white_ratio": 0.0844, "val_mean": 168.0}
    assert classify_lamp_colour(red) == "red"
    # cand_00033 (offset -1, no discontinuity flag): window-edge red bleed.
    assert classify_lamp_colour(
        {"n_px": 210, "red_ratio": 0.8667, "orange_amber_ratio": 0.0143,
         "yellow_ratio": 0.0, "white_ratio": 0.1095, "val_mean": 174.0}
    ) == "red"


def test_classify_lamp_colour_keeps_amber_blend_intermediate():
    # cand_00002 (offset 0, the genuine flip frame): red and amber coexist -> a real transition.
    blend = {"n_px": 552, "red_ratio": 0.393, "orange_amber_ratio": 0.438,
             "yellow_ratio": 0.098, "white_ratio": 0.062, "val_mean": 132.0}
    assert classify_lamp_colour(blend) == "intermediate"
    # Overexposed white-side frame reads very amber -> must NOT be called stable white.
    assert classify_lamp_colour(
        {"n_px": 342, "red_ratio": 0.0, "orange_amber_ratio": 0.789,
         "yellow_ratio": 0.0, "white_ratio": 0.207, "val_mean": 201.0}
    ) == "intermediate"


def test_classify_lamp_colour_flags_stable_white():
    white = {"n_px": 400, "red_ratio": 0.0, "orange_amber_ratio": 0.10,
             "yellow_ratio": 0.0, "white_ratio": 0.55, "val_mean": 205.0}
    assert classify_lamp_colour(white) == "white"


def test_classify_lamp_colour_exact_threshold_boundaries():
    """Pin every gate constant at its boundary so a transposed threshold (0.45 ->
    0.045) cannot survive a green suite (audit DT-7). At-threshold passes; one
    epsilon below falls through to intermediate/unknown."""
    # n_px gate: 16 judges, 15 does not.
    base = {"red_ratio": 0.9, "orange_amber_ratio": 0.05, "yellow_ratio": 0.0,
            "white_ratio": 0.0, "val_mean": 160.0}
    assert classify_lamp_colour({**base, "n_px": 16}) == "red"
    assert classify_lamp_colour({**base, "n_px": 15}) == "unknown"

    # red gate: red_ratio >= 0.45 AND red/warm >= 0.65 AND white <= 0.20.
    red_at = {"n_px": 100, "red_ratio": 0.45, "orange_amber_ratio": 0.242,  # dominance 0.65
              "yellow_ratio": 0.0, "white_ratio": 0.20, "val_mean": 150.0}
    assert classify_lamp_colour(red_at) == "red"
    assert classify_lamp_colour({**red_at, "red_ratio": 0.449}) == "intermediate"
    assert classify_lamp_colour({**red_at, "orange_amber_ratio": 0.25}) == "intermediate"  # dominance < 0.65
    assert classify_lamp_colour({**red_at, "white_ratio": 0.201}) == "intermediate"

    # white gate: white >= 0.30 AND val >= 175 AND red <= 0.10 AND amber <= 0.30.
    white_at = {"n_px": 100, "red_ratio": 0.10, "orange_amber_ratio": 0.30,
                "yellow_ratio": 0.0, "white_ratio": 0.30, "val_mean": 175.0}
    assert classify_lamp_colour(white_at) == "white"
    assert classify_lamp_colour({**white_at, "white_ratio": 0.299}) == "intermediate"
    assert classify_lamp_colour({**white_at, "val_mean": 174.9}) == "intermediate"
    assert classify_lamp_colour({**white_at, "red_ratio": 0.101}) == "intermediate"
    assert classify_lamp_colour({**white_at, "orange_amber_ratio": 0.301}) == "intermediate"
    # yellow counts toward the warm blend signal like the red gate (audit LS-2)
    assert classify_lamp_colour({**white_at, "orange_amber_ratio": 0.15, "yellow_ratio": 0.16}) == "intermediate"
    assert classify_lamp_colour({**white_at, "orange_amber_ratio": 0.15, "yellow_ratio": 0.15}) == "white"

    # lit gate: warm < 0.15 and white < 0.15 -> unknown; at 0.15 it judges.
    assert classify_lamp_colour({"n_px": 100, "red_ratio": 0.149, "white_ratio": 0.149}) == "unknown"
    assert classify_lamp_colour({"n_px": 100, "red_ratio": 0.0, "orange_amber_ratio": 0.15,
                                 "white_ratio": 0.0}) == "intermediate"


def test_non_finite_colour_features_score_zero_not_maximal():
    """NaN ratios used to clamp to 1.0 (min/max NaN poison) and rank HIGH; they must
    read as absent signal instead (audit LS-5)."""
    nan = float("nan")
    assert colour_intermediacy({"n_px": 100, "red_ratio": nan, "white_ratio": nan,
                                "orange_amber_ratio": nan, "yellow_ratio": nan}) == 0.0
    assert classify_lamp_colour({"n_px": 100, "red_ratio": nan, "white_ratio": nan,
                                 "orange_amber_ratio": nan, "yellow_ratio": nan,
                                 "val_mean": nan}) == "unknown"


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
    assert clean["colour_verdict"] == "unknown"  # no colour features available

    # rwy06 + fallback are review flags but do NOT force the ambiguous tier...
    flagged = score(colour={}, frame_offset=0, quality_flags="fallback_left_to_right", runway="06")
    assert flagged["tier"] == TIER_MEDIUM
    assert "rwy06_faa_default" in flagged["review_flag"]

    # ...only an elevation discontinuity makes it suspect -> ambiguous.
    suspect = score(colour={}, frame_offset=0, quality_flags="elev_discontinuity", runway="06")
    assert suspect["tier"] == TIER_AMBIGUOUS
    assert "elev_discontinuity" in suspect["review_flag"]

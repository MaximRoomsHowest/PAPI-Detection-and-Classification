"""Unit tests for the label-gate precedence in workflows/scripts/apply_verification.py.

The decide() three-bucket gate produced the published 487->250 dataset cleanup and was
previously untested (audit DT-8). Loaded by file path because workflows/scripts is a
script directory, not a package; decide() depends only on stdlib + papi.
"""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[3] / "workflows" / "scripts" / "apply_verification.py"
_spec = importlib.util.spec_from_file_location("apply_verification", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
decide = _mod.decide


def test_fallback_identity_excludes_regardless_of_colour():
    decision, _ = decide("fallback_identity", "intermediate")
    assert decision == "ambiguous_review"
    # precedence: identity doubt beats every colour verdict
    assert decide("fallback_identity;elev_discontinuity", "red")[0] == "ambiguous_review"


def test_telemetry_gap_reverts_stable_crops():
    decision, note = decide("elev_discontinuity", "red")
    assert decision == "reverted_telemetry_gap"
    assert "telemetry gap" in note


def test_telemetry_gap_with_intermediate_crop_is_bucketed_for_review():
    """Contradictory signals must not hide among confident reverts (audit WS-4)."""
    decision, note = decide("elev_discontinuity", "intermediate")
    assert decision == "reverted_telemetry_gap_ambiguous_colour"
    assert "HUMAN REVIEW" in note


def test_stable_colour_reverts():
    assert decide("", "red")[0] == "reverted_stable_colour"
    assert decide("", "white")[0] == "reverted_stable_colour"


def test_intermediate_is_accepted_as_colour_confirmed():
    decision, note = decide("", "intermediate")
    assert decision == "accepted_transition"
    assert "colour-confirmed" in note


def test_unknown_colour_is_accepted_but_never_claims_colour_confirmation():
    """A crop too small to judge keeps its flip-anchored acceptance, but the note
    must say the colour signal was unavailable (audit WS-4)."""
    decision, note = decide("", "unknown")
    assert decision == "accepted_transition"
    assert "colour-confirmed" not in note
    assert "unavailable" in note


def test_rwy06_flag_alone_does_not_exclude():
    # rwy06_faa_default annotates (set-angles pending) but is not an exclusion reason.
    assert decide("rwy06_faa_default", "intermediate")[0] == "accepted_transition"

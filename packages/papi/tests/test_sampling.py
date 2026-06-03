"""Tests for `papi.sampling.select_verification_sample`.

The verification sampler picks the CVAT-review subset and tags every chosen frame
with a ``reason``. It is pure pandas, so we can pin its full behaviour:

  * each individual selection criterion fires with the right reason label,
  * frames matching no criterion are excluded,
  * the per-flight index is computed after a deterministic sort, so a shuffled
    input yields an identical (sorted) result,
  * the ``every_n`` / ``transition_margin_deg`` knobs behave at their boundaries,
  * the internal index helper columns are dropped from the output.
"""

from __future__ import annotations

import pandas as pd
from papi.sampling import select_verification_sample


def _frames(n: int, *, folder: str = "F", camera: str = "WideCamera", rtk: int = 50) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "folder": [folder] * n,
            "file": [f"{i:04d}.JPG" for i in range(n)],
            "camera": [camera] * n,
            "rtk_flag": [rtk] * n,
        }
    )


def _states(
    n: int,
    *,
    folder: str = "F",
    global_state: str = "4W",
    margin: float = 5.0,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "folder": [folder] * n,
            "file": [f"{i:04d}.JPG" for i in range(n)],
            "global_state": [global_state] * n,
            "min_angle_margin_deg": [margin] * n,
        }
    )


def _reason_for(sampled: pd.DataFrame, file: str) -> str | None:
    rows = sampled.loc[sampled["file"] == file, "reason"]
    return rows.iloc[0] if len(rows) else None


def test_flight_endpoints_and_stratified_spacing() -> None:
    """First/last frame -> flight_endpoint; every Nth -> stratified; the rest dropped."""
    sampled = select_verification_sample(_frames(10), _states(10), every_n=8)

    # idx 0 is both endpoint and stratified (0 % 8 == 0); idx 8 is stratified; idx 9 is endpoint.
    assert _reason_for(sampled, "0000.JPG") == "flight_endpoint,stratified"
    assert _reason_for(sampled, "0008.JPG") == "stratified"
    assert _reason_for(sampled, "0009.JPG") == "flight_endpoint"
    # Interior non-stratified frames (1..7) are excluded entirely.
    assert sampled["file"].tolist() == ["0000.JPG", "0008.JPG", "0009.JPG"]


def test_every_n_zero_disables_stratified() -> None:
    """every_n=0 must not select stratified frames (guarded by `every_n > 0`)."""
    sampled = select_verification_sample(_frames(6), _states(6), every_n=0)
    # Only the two endpoints qualify.
    assert sampled["file"].tolist() == ["0000.JPG", "0005.JPG"]
    assert set(sampled["reason"]) == {"flight_endpoint"}


def test_each_extra_criterion_fires_with_expected_reason() -> None:
    meta = _frames(5)
    meta["camera"] = ["WideCamera", "ZoomCamera", "WideCamera", "WideCamera", "WideCamera"]
    meta["rtk_flag"] = [50, 50, 16, 50, 50]  # idx 2 is not RTK-Fixed
    states = _states(5)
    states["global_state"] = ["4W", "4W", "4W", "TRANSITION", "4W"]
    states["min_angle_margin_deg"] = [5.0, 5.0, 5.0, 5.0, 0.1]  # idx 4 near boundary

    sampled = select_verification_sample(meta, states, every_n=100, transition_margin_deg=0.3)

    assert _reason_for(sampled, "0001.JPG") == "zoom_camera"
    assert _reason_for(sampled, "0002.JPG") == "rtk_uncertain"
    assert _reason_for(sampled, "0003.JPG") == "transition_state"
    # idx 0 endpoint+stratified; idx 4 endpoint + near_boundary (margin 0.1 < 0.3).
    assert _reason_for(sampled, "0004.JPG") == "flight_endpoint,near_boundary"


def test_near_boundary_threshold_is_strict_less_than() -> None:
    """margin == transition_margin_deg is NOT near_boundary (comparison is `<`)."""
    meta = _frames(5)
    states = _states(5, margin=5.0)
    # Make interior frame 2 sit exactly on the threshold, frame 3 just under it.
    states.loc[2, "min_angle_margin_deg"] = 0.30
    states.loc[3, "min_angle_margin_deg"] = 0.29

    sampled = select_verification_sample(meta, states, every_n=100, transition_margin_deg=0.30)

    # Frame 2 (== threshold) excluded; frame 3 (< threshold) selected.
    assert _reason_for(sampled, "0002.JPG") is None
    assert _reason_for(sampled, "0003.JPG") == "near_boundary"


def test_rtk_50_is_confident_and_nan_does_not_trigger_uncertain() -> None:
    """rtk_flag == 50 means RTK-Fixed (no reason); NaN rtk must not raise or flag."""
    # All RTK-Fixed: only endpoints selected, none flagged rtk_uncertain.
    sampled = select_verification_sample(_frames(4, rtk=50), _states(4), every_n=100)
    assert "rtk_uncertain" not in ",".join(sampled["reason"])

    meta_nan = _frames(4)
    meta_nan["rtk_flag"] = [float("nan")] * 4
    sampled_nan = select_verification_sample(meta_nan, _states(4), every_n=100)
    assert "rtk_uncertain" not in ",".join(sampled_nan["reason"])
    # Endpoints still come through.
    assert sampled_nan["file"].tolist() == ["0000.JPG", "0003.JPG"]


def test_selection_is_deterministic_under_input_shuffle() -> None:
    """Row order of the inputs must not affect the (sorted) output."""
    meta = _frames(12)
    meta["camera"] = ["WideCamera"] * 12
    meta.loc[5, "camera"] = "ZoomCamera"
    meta.loc[9, "rtk_flag"] = 16
    states = _states(12)
    states.loc[7, "global_state"] = "TRANSITION"

    ordered = select_verification_sample(meta, states, every_n=4, transition_margin_deg=0.3)
    shuffled = select_verification_sample(
        meta.sample(frac=1.0, random_state=11).reset_index(drop=True),
        states.sample(frac=1.0, random_state=29).reset_index(drop=True),
        every_n=4,
        transition_margin_deg=0.3,
    )

    assert ordered[["folder", "file", "reason"]].equals(shuffled[["folder", "file", "reason"]])


def test_per_flight_index_is_scoped_to_each_folder() -> None:
    """Endpoints/stratification are per-flight: each folder gets its own idx 0..n-1."""
    meta = pd.concat([_frames(6, folder="A"), _frames(6, folder="B")], ignore_index=True)
    states = pd.concat([_states(6, folder="A"), _states(6, folder="B")], ignore_index=True)

    sampled = select_verification_sample(meta, states, every_n=100)

    # Both flights contribute their own first+last frame as endpoints.
    endpoints = set(zip(sampled["folder"], sampled["file"], strict=True))
    assert ("A", "0000.JPG") in endpoints
    assert ("A", "0005.JPG") in endpoints
    assert ("B", "0000.JPG") in endpoints
    assert ("B", "0005.JPG") in endpoints


def test_helper_columns_dropped_and_reason_present() -> None:
    sampled = select_verification_sample(_frames(8), _states(8), every_n=4)
    assert "reason" in sampled.columns
    assert "idx_in_flight" not in sampled.columns
    assert "size_in_flight" not in sampled.columns
    # Every returned row carries a non-empty reason.
    assert (sampled["reason"] != "").all()

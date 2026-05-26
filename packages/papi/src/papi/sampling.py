"""Verification-sample selection for CVAT pre-annotation review.

We don't review all 4,058 frames; we sample ~15-20% biased toward cases where the auto-label
is most likely wrong or uncertain. The `reason` column on every sampled row records WHY it was
sampled, so the eventual auto-vs-human agreement stat can be sliced by regime.
"""

from __future__ import annotations

import pandas as pd


def select_verification_sample(
    metadata_df: pd.DataFrame,
    lamp_state_df: pd.DataFrame,
    every_n: int = 8,
    transition_margin_deg: float = 0.3,
) -> pd.DataFrame:
    """Return a DataFrame of frames to verify in CVAT, with a `reason` column.

    Selection criteria (a frame is included if ANY of):
      - Nth-from-start within its flight (stratified spacing).
      - `min_angle_margin_deg < transition_margin_deg` (geometric boundary case).
      - `global_state == 'TRANSITION'`.
      - `camera == 'ZoomCamera'`.
      - `rtk_flag != 50` (not RTK Fixed -> lower position confidence).
      - First or last frame in a flight (start/end conditions).
    """
    df = metadata_df.merge(
        lamp_state_df[["folder", "file", "global_state", "min_angle_margin_deg"]],
        on=["folder", "file"],
        how="left",
    )

    # Per-flight index for stratified + first/last marking
    df = df.sort_values(["folder", "file"]).reset_index(drop=True)
    df["idx_in_flight"] = df.groupby("folder").cumcount()
    df["size_in_flight"] = df.groupby("folder")["folder"].transform("size")

    reasons: list[list[str]] = [[] for _ in range(len(df))]

    for i, row in enumerate(df.itertuples(index=False)):
        idx = row.idx_in_flight
        sz = row.size_in_flight
        if idx == 0 or idx == sz - 1:
            reasons[i].append("flight_endpoint")
        if every_n > 0 and idx % every_n == 0:
            reasons[i].append("stratified")
        margin = getattr(row, "min_angle_margin_deg", None)
        if pd.notna(margin) and margin < transition_margin_deg:
            reasons[i].append("near_boundary")
        gs = getattr(row, "global_state", None)
        if gs == "TRANSITION":
            reasons[i].append("transition_state")
        cam = getattr(row, "camera", None)
        if cam == "ZoomCamera":
            reasons[i].append("zoom_camera")
        rtk = getattr(row, "rtk_flag", None)
        if rtk is not None and not pd.isna(rtk) and int(rtk) != 50:
            reasons[i].append("rtk_uncertain")

    df["reason"] = [",".join(r) for r in reasons]
    sampled = df[df["reason"] != ""].copy()
    sampled = sampled.drop(columns=["idx_in_flight", "size_in_flight"])
    return sampled.reset_index(drop=True)

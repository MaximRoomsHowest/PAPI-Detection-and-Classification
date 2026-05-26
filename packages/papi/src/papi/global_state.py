"""Global glidepath state derived from the 4 per-lamp states."""

from __future__ import annotations

from collections.abc import Sequence

GLOBAL_STATES = ("4W", "3W1R", "2W2R", "1W3R", "4R", "TRANSITION")


def derive_global_state(lamps: Sequence[str]) -> str:
    """Map a 4-tuple of per-lamp states (white|red|transition) to one of 6 global states.

    Any lamp in transition shadows the 5 nominal states with `TRANSITION`. The 5 nominal states
    only consider how many lamps are white vs. red.
    """
    if any(s == "transition" for s in lamps):
        return "TRANSITION"
    n_white = sum(1 for s in lamps if s == "white")
    n_red = sum(1 for s in lamps if s == "red")
    if n_white + n_red != 4:
        raise ValueError(f"unexpected lamp states: {lamps}")
    return {4: "4W", 3: "3W1R", 2: "2W2R", 1: "1W3R", 0: "4R"}[n_white]

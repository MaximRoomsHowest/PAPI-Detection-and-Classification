"""Final per-lamp video verdict aggregated by stable ByteTrack identity."""

from collections import Counter

from papi.lamp_state import NUM_PAPI_LAMPS

from app.services.state import lamp_index_by_track
from app.validation.schemas import LampResult


def aggregate_video_lamps(
    track_observations: dict[int, list[tuple]],
) -> list[LampResult]:
    """Final per-lamp video verdict, aggregated by STABLE ByteTrack identity.

    Each lamp's colour is a majority vote over the frames its track was seen;
    tracks map to lamp 1..4 left-to-right via ``lamp_index_by_track`` (the same
    identity the transition detector uses). Keying off track id rather than the
    per-frame left-to-right rank prevents a dropped/re-ordered frame from mixing
    observations of different physical lamps. Tuples: (frame, color, center_x, conf, redness).
    """
    index_by_track = lamp_index_by_track(track_observations)
    obs_by_index: dict[int, list[tuple]] = {}
    for tid, obs in track_observations.items():
        index = index_by_track.get(tid)
        if index is not None:
            obs_by_index.setdefault(index, []).extend(obs)

    final_lamps: list[LampResult] = []
    for index in range(1, NUM_PAPI_LAMPS + 1):
        obs = obs_by_index.get(index, [])
        if not obs:
            final_lamps.append(LampResult(index=index, state="obscured", confidence=0.0))
            continue
        state = Counter(o[1] for o in obs).most_common(1)[0][0]
        matching = [o for o in obs if o[1] == state]
        confidence = round(sum(o[3] for o in matching) / len(matching), 4)
        final_lamps.append(LampResult(index=index, state=state, confidence=confidence))
    return final_lamps

"""Tests for ``app.services.telemetry`` — DJI SRT / CSV / JSON telemetry parsing.

Pins the contract the analyze endpoints rely on:
  * each format parses lat/lon + an ABSOLUTE altitude into validated samples,
  * a relative-altitude-only file (DJI ``rel_alt`` / barometer) is rejected,
  * out-of-range fixes are dropped but a single good fix still parses,
  * empty / malformed / unknown content raises ``TelemetryError`` (a ValueError),
  * ``resample_to_frames`` aligns a track to a frame count (index-aware + proportional).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.telemetry import (
    DroneSample,
    TelemetryError,
    parse_telemetry,
    resample_to_frames,
)

_FIXTURES = Path(__file__).parent / "fixtures"

# --- DJI SRT -----------------------------------------------------------------

_SRT_MODERN = """1
00:00:00,000 --> 00:00:00,033
<font size="28">SrtCnt : 1, DiffTime : 33ms
2026-04-29 00:07:00.000
[iso : 100] [shutter : 1/60.0] [fnum : 2.8] [focal_len : 24.00] [latitude: 47.673521] [longitude: 9.518154] [rel_alt: 50.000 abs_alt: 520.000]</font>

2
00:00:00,033 --> 00:00:00,066
<font size="28">SrtCnt : 2, DiffTime : 33ms
2026-04-29 00:07:00.033
[iso : 100] [shutter : 1/60.0] [fnum : 2.8] [focal_len : 24.00] [latitude: 47.673600] [longitude: 9.518200] [rel_alt: 55.000 abs_alt: 525.500]</font>

3
00:00:00,066 --> 00:00:00,099
<font size="28">SrtCnt : 3, DiffTime : 33ms
2026-04-29 00:07:00.066
[iso : 100] [shutter : 1/60.0] [fnum : 2.8] [focal_len : 24.00] [latitude: 47.673700] [longitude: 9.518250] [rel_alt: 60.000 abs_alt: 530.250]</font>
"""


def test_srt_modern_bracketed_parses_all_cues() -> None:
    samples = parse_telemetry("DJI_0001.SRT", _SRT_MODERN.encode("utf-8"))
    assert len(samples) == 3
    first = samples[0]
    assert first.latitude == pytest.approx(47.673521)
    assert first.longitude == pytest.approx(9.518154)
    # abs_alt is used, NOT rel_alt.
    assert first.altitude_m == pytest.approx(520.000)
    # Counter is 1-based in the file -> 0-based frame_index.
    assert first.frame_index == 0
    assert samples[1].frame_index == 1
    assert first.time_s == pytest.approx(0.0)
    assert samples[2].time_s == pytest.approx(0.066)
    # Altitude climbs across the descent sweep.
    assert [s.altitude_m for s in samples] == pytest.approx([520.0, 525.5, 530.25])


def test_srt_spaced_colons_and_bom() -> None:
    text = (
        "﻿1\n"
        "00:00:01,000 --> 00:00:01,033\n"
        "[ latitude : -12.5 ] [ longitude : 130.8 ] [ abs_alt : 95.4 ]\n"
    )
    samples = parse_telemetry("track.srt", text.encode("utf-8"))
    assert len(samples) == 1
    assert samples[0].latitude == pytest.approx(-12.5)
    assert samples[0].longitude == pytest.approx(130.8)
    assert samples[0].altitude_m == pytest.approx(95.4)


def test_srt_relative_altitude_only_is_rejected() -> None:
    # rel_alt present but no abs_alt -> not a usable WGS-84 height -> no samples.
    text = "1\n00:00:00,000 --> 00:00:00,033\n[latitude: 47.6] [longitude: 9.5] [rel_alt: 50.0]\n"
    with pytest.raises(TelemetryError):
        parse_telemetry("rel.srt", text.encode("utf-8"))


def test_srt_gps_paren_order_lon_then_lat() -> None:
    # Older DJI "GPS(lon,lat,sat)" layout — longitude is written FIRST. A separate
    # bracketed abs_alt supplies the usable absolute height.
    text = (
        "1\n00:00:00,000 --> 00:00:00,033\n"
        "HOME(9.5182,47.6735) GPS(9.5182,47.6735,16) [abs_alt: 511.0]\n"
    )
    samples = parse_telemetry("old.srt", text.encode("utf-8"))
    assert len(samples) == 1
    assert samples[0].latitude == pytest.approx(47.6735)
    assert samples[0].longitude == pytest.approx(9.5182)
    assert samples[0].altitude_m == pytest.approx(511.0)


# --- CSV ---------------------------------------------------------------------


def test_csv_with_header_and_aliases() -> None:
    text = "lat,lon,abs_alt\n47.6,9.5,520\n47.61,9.51,522\n"
    samples = parse_telemetry("flight.csv", text.encode("utf-8"))
    assert [(round(s.latitude, 2), round(s.longitude, 2), s.altitude_m) for s in samples] == [
        (47.6, 9.5, 520.0),
        (47.61, 9.51, 522.0),
    ]
    assert samples[0].frame_index == 0 and samples[1].frame_index == 1


def test_csv_semicolon_delimiter_and_frame_column() -> None:
    text = "frame;latitude;longitude;altitude_m\n10;47.6;9.5;520\n11;47.6;9.5;521\n"
    samples = parse_telemetry("f.csv", text.encode("utf-8"))
    assert len(samples) == 2
    assert samples[0].frame_index == 10
    assert samples[1].altitude_m == pytest.approx(521)


def test_csv_headerless_assumes_lat_lon_alt() -> None:
    text = "47.6,9.5,520\n47.7,9.6,540\n"
    samples = parse_telemetry("nohdr.csv", text.encode("utf-8"))
    assert len(samples) == 2
    assert samples[0].latitude == pytest.approx(47.6)
    assert samples[0].altitude_m == pytest.approx(520)


def test_csv_drops_out_of_range_row_keeps_valid() -> None:
    text = "latitude,longitude,altitude_m\n999,9.5,520\n47.6,9.5,520\n"
    samples = parse_telemetry("mixed.csv", text.encode("utf-8"))
    assert len(samples) == 1
    assert samples[0].latitude == pytest.approx(47.6)


def test_csv_missing_altitude_column_is_unusable() -> None:
    text = "latitude,longitude\n47.6,9.5\n"
    with pytest.raises(TelemetryError):
        parse_telemetry("noalt.csv", text.encode("utf-8"))


# --- JSON --------------------------------------------------------------------


def test_json_array_of_objects() -> None:
    text = '[{"latitude":47.6,"longitude":9.5,"altitude_m":520},{"lat":47.7,"lng":9.6,"abs_alt":540}]'
    samples = parse_telemetry("t.json", text.encode("utf-8"))
    assert len(samples) == 2
    assert samples[1].latitude == pytest.approx(47.7)
    assert samples[1].altitude_m == pytest.approx(540)


def test_json_single_object() -> None:
    text = '{"latitude": 47.6, "longitude": 9.5, "altitude_m": 520}'
    samples = parse_telemetry("one.json", text.encode("utf-8"))
    assert len(samples) == 1
    assert samples[0].longitude == pytest.approx(9.5)


def test_json_samples_container() -> None:
    text = '{"samples":[{"lat":47.6,"lon":9.5,"alt":520,"frame_index":4}]}'
    samples = parse_telemetry("c.json", text.encode("utf-8"))
    assert len(samples) == 1
    assert samples[0].frame_index == 4


# --- auto-detect + errors ----------------------------------------------------


def test_autodetect_json_without_extension() -> None:
    text = '[{"latitude":47.6,"longitude":9.5,"altitude_m":520}]'
    samples = parse_telemetry("blob", text.encode("utf-8"))
    assert len(samples) == 1


def test_autodetect_srt_without_extension() -> None:
    text = "1\n00:00:00,000 --> 00:00:00,033\n[latitude: 47.6] [longitude: 9.5] [abs_alt: 520]\n"
    samples = parse_telemetry("noext", text.encode("utf-8"))
    assert len(samples) == 1


def test_empty_file_raises() -> None:
    with pytest.raises(TelemetryError):
        parse_telemetry("e.srt", b"   \n  ")


def test_garbage_raises() -> None:
    with pytest.raises(TelemetryError):
        parse_telemetry("g.csv", b"not telemetry at all\njust prose\n")


# --- resample_to_frames ------------------------------------------------------


def test_resample_index_aware_nearest() -> None:
    samples = [
        DroneSample(47.0, 9.0, 500.0, frame_index=0),
        DroneSample(47.0, 9.0, 510.0, frame_index=10),
    ]
    out = resample_to_frames(samples, frame_count=11)
    assert len(out) == 11
    # Frames near 0 take the first fix, frames near 10 take the second.
    assert out[0].altitude_m == 500.0
    assert out[10].altitude_m == 510.0
    assert out[4].altitude_m == 500.0  # |4-0|=4 < |4-10|=6
    assert out[6].altitude_m == 510.0  # |6-10|=4 < |6-0|=6


def test_resample_proportional_without_indices() -> None:
    samples = [
        DroneSample(47.0, 9.0, 500.0, frame_index=None),
        DroneSample(47.0, 9.0, 520.0, frame_index=None),
        DroneSample(47.0, 9.0, 540.0, frame_index=None),
    ]
    out = resample_to_frames(samples, frame_count=5)
    assert [s.altitude_m for s in out] == [500.0, 500.0, 520.0, 540.0, 540.0]


def test_resample_single_frame_takes_middle() -> None:
    samples = [DroneSample(47.0, 9.0, a, frame_index=i) for i, a in enumerate([500.0, 520.0, 540.0])]
    out = resample_to_frames(samples, frame_count=1)
    assert len(out) == 1 and out[0].altitude_m == 520.0


def test_resample_empty_inputs() -> None:
    assert resample_to_frames([], 10) == []
    assert resample_to_frames([DroneSample(47.0, 9.0, 500.0)], 0) == []


# --- shipped sample fixtures -------------------------------------------------


@pytest.mark.parametrize("filename", ["sample_descent.srt", "sample_descent.csv", "sample_descent.json"])
def test_sample_fixture_files_parse_consistently(filename: str) -> None:
    """The three shipped sample telemetry files describe the SAME EDNY rwy-24 descent,
    so all three must parse to the same 10-fix track (10 frames, altitude 520 -> 484)."""
    samples = parse_telemetry(filename, (_FIXTURES / filename).read_bytes())
    assert len(samples) == 10
    assert [s.frame_index for s in samples] == list(range(10))
    assert samples[0].altitude_m == pytest.approx(520.0)
    assert samples[-1].altitude_m == pytest.approx(484.0)
    # Altitude descends monotonically across the sweep.
    altitudes = [s.altitude_m for s in samples]
    assert altitudes == sorted(altitudes, reverse=True)
    # All fixes sit just north of the EDNY rwy-24 PAPI.
    assert all(47.67 < s.latitude < 47.69 and 9.51 < s.longitude < 9.52 for s in samples)

"""Tests for `papi.metadata` — EXIF + DJI-XMP per-image metadata extraction.

The production code never decodes pixels: it reads the first ~96 KB for the XMP
packet and asks PIL for the EXIF header only. We therefore build tiny synthetic
JPEGs with PIL's native EXIF writer (no extra deps) and *append* a DJI-style XMP
packet to the file bytes — `metadata._read_head` reads it back from the head
buffer exactly like a real DJI M4E frame.

These tests pin:
  * the pure scalar parsers (`_to_float`, `_to_int`, `_dms_to_dd`) including the
    truncate-toward-zero and missing/empty-field behaviour,
  * `_parse_xmp` only matching the `drone-dji:` namespace,
  * `_extract_exif` round-tripping GPS DMS -> signed decimal degrees,
  * `extract_image_metadata` preferring XMP-RTK lat/lon over EXIF GPS, coercing
    types, and degrading missing fields to ``None`` rather than raising.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from papi.metadata import (
    _dms_to_dd,
    _parse_xmp,
    _to_float,
    _to_int,
    extract_image_metadata,
)
from PIL import Image
from PIL.ExifTags import GPS, IFD, Base
from PIL.TiffImagePlugin import IFDRational

# ---------------------------------------------------------------------------
# scalar parsers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("3.14", 3.14),
        ("-12.30", -12.30),
        ("+465.42", 465.42),
        (50, 50.0),
        ("", None),
        (None, None),
        ("not-a-number", None),
    ],
)
def test_to_float(raw, expected) -> None:
    assert _to_float(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("50", 50),
        ("50.0", 50),  # tolerate trailing '.0'
        ("-1.9", -1),  # int(float(...)) truncates toward zero
        (16, 16),
        ("", None),
        (None, None),
        ("junk", None),
    ],
)
def test_to_int(raw, expected) -> None:
    assert _to_int(raw) == expected


def test_dms_to_dd_north_is_positive() -> None:
    # 47° 40' 7.716" N == 47.66881°
    assert _dms_to_dd((47.0, 40.0, 7.716), "N") == pytest.approx(47.66881, abs=1e-5)


def test_dms_to_dd_west_is_negative() -> None:
    # W and S flip the sign.
    assert _dms_to_dd((9.0, 30.0, 0.0), "W") == pytest.approx(-9.5, abs=1e-9)
    assert _dms_to_dd((1.0, 0.0, 0.0), "S") == pytest.approx(-1.0, abs=1e-9)


def test_dms_to_dd_none_and_malformed_return_none() -> None:
    assert _dms_to_dd(None, "N") is None
    assert _dms_to_dd((1.0, 2.0), "N") is None  # missing seconds -> IndexError -> None


# ---------------------------------------------------------------------------
# _parse_xmp
# ---------------------------------------------------------------------------


def test_parse_xmp_extracts_only_drone_dji_namespace() -> None:
    buf = (
        b'<x drone-dji:GimbalYawDegree="-12.3" '
        b"drone-dji:RtkFlag='50' "  # single-quoted value
        b'tiff:Make="DJI" '  # different namespace, must be ignored
        b'drone-dji:ImageSource="WideCamera" />'
    )
    out = _parse_xmp(buf)
    assert out == {
        "GimbalYawDegree": "-12.3",
        "RtkFlag": "50",
        "ImageSource": "WideCamera",
    }
    assert "Make" not in out


def test_parse_xmp_empty_buffer_returns_empty_dict() -> None:
    assert _parse_xmp(b"no xmp packet here") == {}


# ---------------------------------------------------------------------------
# JPEG fixture helpers
# ---------------------------------------------------------------------------


def _write_jpeg_with_exif_gps(
    path: Path,
    *,
    lat_ref: str = "N",
    lon_ref: str = "E",
) -> None:
    """Write a tiny JPEG carrying EXIF GPS (47° 40' N, 9° 30' E) + a few header tags."""
    img = Image.new("RGB", (64, 48), (10, 20, 30))
    exif = img.getexif()
    exif[Base.DateTime] = "2026:04:28 19:26:56"
    exif[Base.FocalLengthIn35mmFilm] = 24

    exif_ifd = exif.get_ifd(IFD.Exif)
    exif_ifd[Base.ExifImageWidth] = 5280
    exif_ifd[Base.ExifImageHeight] = 3956
    exif_ifd[Base.ISOSpeedRatings] = 200
    exif_ifd[Base.ExposureTime] = IFDRational(1, 200)
    exif_ifd[Base.FNumber] = IFDRational(28, 10)

    gps = exif.get_ifd(IFD.GPSInfo)
    gps[GPS.GPSLatitudeRef] = lat_ref
    gps[GPS.GPSLatitude] = (IFDRational(47), IFDRational(40), IFDRational(0))
    gps[GPS.GPSLongitudeRef] = lon_ref
    gps[GPS.GPSLongitude] = (IFDRational(9), IFDRational(30), IFDRational(0))

    img.save(path, exif=exif)


def _append_xmp(path: Path, fields: dict[str, str]) -> None:
    """Append a DJI-style XMP packet to an existing JPEG's bytes (head buffer)."""
    body = b" ".join(f'drone-dji:{k}="{v}"'.encode("ascii") for k, v in fields.items())
    packet = b'<?xpacket begin="?"?><x:xmpmeta xmlns:drone-dji="x">' + body + b"</x:xmpmeta>"
    path.write_bytes(path.read_bytes() + packet)


# ---------------------------------------------------------------------------
# _extract_exif (via the public function path) and end-to-end extraction
# ---------------------------------------------------------------------------


def test_extract_exif_fields_and_gps_roundtrip(tmp_path: Path) -> None:
    """EXIF-only frame (no XMP): header tags + GPS DMS->DD survive the round-trip."""
    jpg = tmp_path / "flightA" / "DJI_0001_V.JPG"
    jpg.parent.mkdir()
    _write_jpeg_with_exif_gps(jpg)

    meta = extract_image_metadata(jpg)

    assert meta["folder"] == "flightA"
    assert meta["file"] == "DJI_0001_V.JPG"
    assert meta["image_width"] == 5280
    assert meta["image_height"] == 3956
    assert meta["focal_35mm"] == 24
    assert meta["iso"] == 200
    assert meta["f_number"] == pytest.approx(2.8)
    # ExposureTime is stringified from the EXIF rational; only its presence is contractual.
    assert isinstance(meta["exposure_s"], str) and meta["exposure_s"]
    assert meta["local_datetime"] == "2026:04:28 19:26:56"
    # No XMP packet -> lat/lon fall back to EXIF GPS (47°40' N, 9°30' E).
    assert meta["lat"] == pytest.approx(47.0 + 40.0 / 60.0, abs=1e-6)
    assert meta["lon"] == pytest.approx(9.0 + 30.0 / 60.0, abs=1e-6)


def test_extract_exif_gps_southwest_refs_flip_sign(tmp_path: Path) -> None:
    jpg = tmp_path / "DJI_0002_V.JPG"
    _write_jpeg_with_exif_gps(jpg, lat_ref="S", lon_ref="W")
    meta = extract_image_metadata(jpg)
    assert meta["lat"] == pytest.approx(-(47.0 + 40.0 / 60.0), abs=1e-6)
    assert meta["lon"] == pytest.approx(-(9.0 + 30.0 / 60.0), abs=1e-6)


def test_extract_metadata_prefers_xmp_rtk_over_exif_and_coerces_types(tmp_path: Path) -> None:
    """The authoritative RTK lat/lon from XMP must override EXIF GPS, and the
    various typed fields must be coerced (float / int) per the schema."""
    jpg = tmp_path / "flightB" / "DJI_0003_V.JPG"
    jpg.parent.mkdir()
    _write_jpeg_with_exif_gps(jpg)  # EXIF GPS ~47.667 / 9.5
    _append_xmp(
        jpg,
        {
            "GpsLatitude": "47.123456",
            "GpsLongitude": "9.654321",
            "AbsoluteAltitude": "+465.42",
            "RelativeAltitude": "+120.30",
            "GimbalYawDegree": "-12.30",
            "GimbalPitchDegree": "-25.10",
            "GimbalRollDegree": "0.00",
            "RtkFlag": "50",
            "ImageSource": "WideCamera",
            "LRFStatus": "Normal",
            "LRFTargetDistance": "512.30",
            "UTCAtExposure": "2026:04:28 17:26:56",
        },
    )

    meta = extract_image_metadata(jpg)

    # XMP RTK position wins over the EXIF GPS values.
    assert meta["lat"] == pytest.approx(47.123456, abs=1e-6)
    assert meta["lon"] == pytest.approx(9.654321, abs=1e-6)
    assert meta["alt_ellipsoidal_m"] == pytest.approx(465.42)
    assert meta["agl_m"] == pytest.approx(120.30)
    assert meta["gimbal_yaw_deg"] == pytest.approx(-12.30)
    assert meta["gimbal_pitch_deg"] == pytest.approx(-25.10)
    # RtkFlag is coerced to int (not the raw "50" string).
    assert meta["rtk_flag"] == 50
    assert isinstance(meta["rtk_flag"], int)
    assert meta["camera"] == "WideCamera"
    assert meta["lrf_status"] == "Normal"
    assert meta["lrf_target_distance_m"] == pytest.approx(512.30)
    # String fields pass through verbatim.
    assert meta["utc_exposure"] == "2026:04:28 17:26:56"
    # EXIF-sourced header fields still populated alongside XMP.
    assert meta["image_width"] == 5280
    assert meta["camera"] == "WideCamera"


def test_extract_metadata_missing_xmp_fields_are_none(tmp_path: Path) -> None:
    """Fields absent from the XMP packet degrade to ``None`` (never raise)."""
    jpg = tmp_path / "DJI_0004_V.JPG"
    _write_jpeg_with_exif_gps(jpg)
    _append_xmp(jpg, {"ImageSource": "ZoomCamera"})  # only one field present

    meta = extract_image_metadata(jpg)

    assert meta["camera"] == "ZoomCamera"
    # Every other XMP-sourced field is None.
    for key in (
        "agl_m",
        "gimbal_yaw_deg",
        "flight_yaw_deg",
        "speed_x_mps",
        "rtk_flag",
        "rtk_std_lat_m",
        "lrf_status",
        "lrf_target_distance_m",
        "sensor_temperature_c",
        "utc_exposure",
    ):
        assert meta[key] is None, f"expected {key} to be None when absent from XMP"


def test_extract_metadata_empty_xmp_latlon_falls_back_to_exif(tmp_path: Path) -> None:
    """An empty XMP GpsLatitude value (truthiness guard) triggers the EXIF fallback."""
    jpg = tmp_path / "DJI_0005_V.JPG"
    _write_jpeg_with_exif_gps(jpg)
    _append_xmp(jpg, {"GpsLatitude": "", "GpsLongitude": ""})

    meta = extract_image_metadata(jpg)
    # Empty XMP -> EXIF GPS used instead.
    assert meta["lat"] == pytest.approx(47.0 + 40.0 / 60.0, abs=1e-6)
    assert meta["lon"] == pytest.approx(9.0 + 30.0 / 60.0, abs=1e-6)


def test_extract_metadata_unreadable_jpeg_without_xmp_degrades_to_none(tmp_path: Path) -> None:
    """A file PIL cannot open (corrupt/truncated) makes _extract_exif return {}; with no
    XMP GPS the lat/lon fallback must degrade to None, not KeyError on the empty EXIF dict
    (which crashed the whole ~4000-frame pipeline pass on one bad frame) — audit."""
    bad = tmp_path / "DJI_corrupt.JPG"
    bad.write_bytes(b"not a decodable image \x00\xff and no drone-dji xmp packet")
    meta = extract_image_metadata(bad)
    assert meta["lat"] is None
    assert meta["lon"] is None
    assert meta["file"] == "DJI_corrupt.JPG"

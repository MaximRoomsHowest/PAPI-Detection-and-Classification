import pytest
from fastapi import HTTPException

from app.validation.analyze import parse_manual_drone_metadata


def test_parse_manual_drone_metadata_accepts_empty_metadata():
    assert parse_manual_drone_metadata(None, None, None) is None


def test_parse_manual_drone_metadata_requires_all_values():
    with pytest.raises(HTTPException):
        parse_manual_drone_metadata(47.0, None, 465.0)


def test_parse_manual_drone_metadata_returns_coordinate_tuple():
    assert parse_manual_drone_metadata(47.0, 9.0, 465.0) == (47.0, 9.0, 465.0)


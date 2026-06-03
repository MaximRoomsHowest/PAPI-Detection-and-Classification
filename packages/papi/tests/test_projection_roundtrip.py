"""`ProjectionConvention` (de)serialisation roundtrip tests.

The existing ``test_projection.py`` uses ``from_dict`` to load the calibrated
convention but never asserts the ``to_dict`` <-> ``from_dict`` contract itself.
That contract matters: ``pipeline.py calibrate`` writes ``to_dict()`` output to
``configs/projection.yaml`` and the inference path reads it back via
``from_dict``. A drift between the two would silently corrupt the camera model.

We pin:
  * a full roundtrip preserves every field (matrices via ``np.array_equal``),
  * ``to_dict`` emits plain (YAML/JSON-serialisable) Python types,
  * ``from_dict`` coerces input types and defaults ``invert_rotation`` to False,
  * the loaded ``DEFAULT_CONVENTION`` survives a roundtrip unchanged.
"""

from __future__ import annotations

import numpy as np
import pytest
from papi.projection import DEFAULT_CONVENTION, ProjectionConvention


def _sample_dict() -> dict:
    return {
        "enu_to_intermediate": [[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]],
        "euler_order": "ZYX",
        "yaw_sign": 1,
        "pitch_sign": -1,
        "roll_sign": 1,
        "body_to_image": [[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]],
        "invert_rotation": True,
    }


def _assert_conventions_equal(a: ProjectionConvention, b: ProjectionConvention) -> None:
    """Field-wise equality. NOTE: we cannot use ``a == b`` — the frozen dataclass
    holds numpy arrays, so the auto-generated ``__eq__`` raises ValueError
    (ambiguous array truth value). See test_eq_raises_on_array_fields below."""
    assert np.array_equal(a.enu_to_intermediate, b.enu_to_intermediate)
    assert np.array_equal(a.body_to_image, b.body_to_image)
    assert a.euler_order == b.euler_order
    assert a.yaw_sign == b.yaw_sign
    assert a.pitch_sign == b.pitch_sign
    assert a.roll_sign == b.roll_sign
    assert a.invert_rotation == b.invert_rotation


def test_from_dict_to_dict_roundtrip_preserves_all_fields() -> None:
    d = _sample_dict()
    conv = ProjectionConvention.from_dict(d)
    back = conv.to_dict()

    assert back["enu_to_intermediate"] == d["enu_to_intermediate"]
    assert back["body_to_image"] == d["body_to_image"]
    assert back["euler_order"] == "ZYX"
    assert back["yaw_sign"] == 1
    assert back["pitch_sign"] == -1
    assert back["roll_sign"] == 1
    assert back["invert_rotation"] is True

    # to_dict -> from_dict reconstructs an equivalent object.
    _assert_conventions_equal(ProjectionConvention.from_dict(back), conv)


def test_to_dict_emits_plain_serialisable_types() -> None:
    """No numpy types leak out, so yaml.safe_dump / json.dumps can handle it."""
    d = ProjectionConvention.from_dict(_sample_dict()).to_dict()
    assert isinstance(d["enu_to_intermediate"], list)
    assert isinstance(d["enu_to_intermediate"][0], list)
    assert all(isinstance(x, float) for row in d["enu_to_intermediate"] for x in row)
    assert isinstance(d["body_to_image"], list)
    assert isinstance(d["euler_order"], str)
    assert isinstance(d["yaw_sign"], int)
    assert isinstance(d["invert_rotation"], bool)


def test_from_dict_coerces_input_types() -> None:
    """String/whole-number inputs are coerced to the declared field types."""
    d = _sample_dict()
    d["yaw_sign"] = "1"  # string -> int
    d["euler_order"] = 123  # non-str -> str
    d["enu_to_intermediate"] = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]  # ints -> float array
    conv = ProjectionConvention.from_dict(d)

    assert conv.yaw_sign == 1 and isinstance(conv.yaw_sign, int)
    assert conv.euler_order == "123" and isinstance(conv.euler_order, str)
    assert conv.enu_to_intermediate.dtype == np.dtype(float)


def test_from_dict_defaults_invert_rotation_to_false_when_missing() -> None:
    d = _sample_dict()
    del d["invert_rotation"]
    conv = ProjectionConvention.from_dict(d)
    assert conv.invert_rotation is False


def test_default_convention_roundtrips_unchanged() -> None:
    """The module-level DEFAULT_CONVENTION survives to_dict -> from_dict intact."""
    back = ProjectionConvention.from_dict(DEFAULT_CONVENTION.to_dict())
    _assert_conventions_equal(back, DEFAULT_CONVENTION)
    # Spot-check the documented default values.
    assert DEFAULT_CONVENTION.euler_order == "ZYX"
    assert DEFAULT_CONVENTION.pitch_sign == -1
    assert DEFAULT_CONVENTION.invert_rotation is False


def test_eq_raises_on_array_fields() -> None:
    """Document real behaviour: ``==`` on two conventions raises because the
    dataclass contains numpy arrays. Callers must compare field-wise (helpers
    above) — this test pins the gotcha so an accidental ``==`` is caught."""
    other = ProjectionConvention.from_dict(DEFAULT_CONVENTION.to_dict())
    with pytest.raises(ValueError):
        _ = DEFAULT_CONVENTION == other

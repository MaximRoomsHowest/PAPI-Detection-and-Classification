"""The curated public API (audit IMP-ML-1) stays importable and stable."""

import papi


def test_version_and_metadata_exposed():
    assert papi.__version__
    assert papi.__author__
    assert papi.__url__


def test_every_public_name_resolves():
    for name in papi.__all__:
        assert hasattr(papi, name), f"papi.{name} is declared in __all__ but missing"


def test_derive_global_state_via_top_level_import():
    assert papi.derive_global_state(["white", "white", "red", "red"]) == "2W2R"
    assert papi.derive_global_state(["white", "white", "white", "white"]) == "4W"

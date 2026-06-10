"""Shared test fixtures.

The backend Settings reads ``PAPI_*`` environment variables (and apps/backend/.env).
A developer shell exporting e.g. ``PAPI_TRANSITION_MODEL_PATH`` would silently change
registry resolution inside tests and flip assertions (audit DT-2). Strip every
``PAPI_*`` variable before each test so the suite is hermetic; tests that need one
set it explicitly via ``monkeypatch.setenv`` (which runs after this fixture).
"""

import os

import pytest


@pytest.fixture(autouse=True)
def _hermetic_papi_env(monkeypatch):
    for name in list(os.environ):
        if name.startswith("PAPI_"):
            monkeypatch.delenv(name, raising=False)

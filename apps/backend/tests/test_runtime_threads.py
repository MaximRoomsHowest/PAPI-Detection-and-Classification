import os

from app.runtime_threads import _THREAD_ENV_VARS, resolve_thread_count, set_thread_env


def test_resolve_thread_count_honors_explicit_positive():
    assert resolve_thread_count(3) == 3


def test_resolve_thread_count_auto_is_at_least_one():
    # 0 == auto: must resolve to a usable, >=1 count on every platform (cgroup-aware on
    # Linux, os.cpu_count() elsewhere).
    assert resolve_thread_count(0) >= 1


def test_resolve_thread_count_treats_negative_as_auto():
    assert resolve_thread_count(-5) >= 1


def test_set_thread_env_sets_all_native_math_vars(monkeypatch):
    for var in _THREAD_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    set_thread_env(2)
    for var in _THREAD_ENV_VARS:
        assert os.environ[var] == "2"

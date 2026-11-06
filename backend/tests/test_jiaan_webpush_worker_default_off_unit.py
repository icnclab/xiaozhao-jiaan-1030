"""Pure-logic / static tests confirming the still-uncommitted worker.py Web
Push sweep block stays off by default and never calls sweep()/dispatch_due()
unguarded. No database connection, no network call, no real push sent.
"""
import os
import re
from pathlib import Path
from unittest.mock import patch

from app.services import jiaan_webpush

ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = (ROOT / "app" / "worker.py").read_text(encoding="utf-8")


def test_webpush_disabled_by_default_without_env_var():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("JIAAN_WEBPUSH_DISPATCH", None)
        assert jiaan_webpush.enabled() is False


def test_webpush_disabled_for_any_value_other_than_on():
    for value in ("off", "", "0", "false", "ON ", "yes"):
        with patch.dict(os.environ, {"JIAAN_WEBPUSH_DISPATCH": value}):
            assert jiaan_webpush.enabled() is (value.strip().lower() == "on")


def test_webpush_enabled_only_when_env_var_is_exactly_on():
    with patch.dict(os.environ, {"JIAAN_WEBPUSH_DISPATCH": "on"}):
        assert jiaan_webpush.enabled() is True
    with patch.dict(os.environ, {"JIAAN_WEBPUSH_DISPATCH": "ON"}):
        assert jiaan_webpush.enabled() is True  # case-insensitive per enabled()'s own .lower()


def test_worker_webpush_block_is_guarded_by_enabled_before_sweep_or_dispatch():
    # Regression guard: the block that calls sweep()/dispatch_due() must be
    # inside an `if jiaan_webpush.enabled() and ...` condition, not called
    # unconditionally.
    match = re.search(
        r"if jiaan_webpush\.enabled\(\)[^\n]*:\n((?:.*\n)*?)\s*last_webpush = now",
        WORKER_SOURCE,
    )
    assert match, "worker.py 找不到以 jiaan_webpush.enabled() 守衛的區塊"
    block = match.group(1)
    assert "jiaan_webpush.sweep(" in block
    assert "jiaan_webpush.dispatch_due(" in block
    # Every DB write in the guarded block must be wrapped in try/except so a
    # misconfigured or missing-table environment cannot crash the worker loop.
    assert "try:" in block and "except Exception" in block


def test_worker_webpush_block_rolls_back_and_closes_session_on_failure():
    match = re.search(
        r"if jiaan_webpush\.enabled\(\)[^\n]*:\n((?:.*\n)*?)\s*last_webpush = now",
        WORKER_SOURCE,
    )
    block = match.group(1)
    assert "session.rollback()" in block
    assert "session.close()" in block

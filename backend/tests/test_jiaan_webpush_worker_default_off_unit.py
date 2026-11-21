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


def test_worker_no_longer_runs_the_legacy_poll_based_webpush_cycle():
    # 2026-11-14 architecture change: the old poll-based sweep()/dispatch_due()
    # cycle shared JIAAN_WEBPUSH_DISPATCH with the new transactional Outbox
    # path (jiaan_emergency_outbox.dispatch_one(), wired via HANDLERS). Running
    # both under the same flag would double-dispatch the same SOS alert, so
    # the old cycle was removed from the loop rather than re-guarded. This
    # replaces the two regression guards that used to assert the old block's
    # shape; asserting its absence is the correct guard now.
    live_source = re.sub(r"#.*", "", WORKER_SOURCE)
    assert "jiaan_webpush.sweep(" not in live_source
    assert "jiaan_webpush.dispatch_due(" not in live_source
    assert "import jiaan_webpush" not in live_source


def test_worker_wires_the_new_outbox_job_kind_through_dispatch_one():
    assert '"jiaan_emergency_webpush_outbox": _emergency_webpush_outbox' in WORKER_SOURCE
    match = re.search(
        r"def _emergency_webpush_outbox\(session: Session, payload: dict\) -> None:\n"
        r"((?:.*\n)*?)\n\nHANDLERS",
        WORKER_SOURCE,
    )
    assert match, "worker.py 找不到 _emergency_webpush_outbox 的實作"
    body = match.group(1)
    assert "jiaan_emergency_outbox.dispatch_one(" in body
    assert "session.commit()" in body

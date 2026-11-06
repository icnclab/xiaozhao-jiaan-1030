"""Static text checks for app/static/fieldtest-dashboard.html -- the vanilla
HTML/JS admin dashboard served by fieldtest_routes.xz_fieldtest_dashboard_page().
This file is not part of the Vite/React frontend build, so there is no
existing jsdom/vitest harness for it; these are pure regex checks against
the source text, not a DOM/browser execution test.

Covers this round's additions: the mapping-entry form (previously missing --
the dashboard could only view stats/export, never actually map a code to a
user), and surfacing the backend's actual error `detail` text instead of a
generic message (so a 503 "table not yet created" response is readable, not
indistinguishable from any other failure).
"""
import re
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1] / "app" / "static" / "fieldtest-dashboard.html").read_text(encoding="utf-8")


def test_mappings_endpoint_is_registered():
    assert "'/api/fieldtest/mappings'" in HTML


def test_mapping_form_posts_code_and_user_id_as_json():
    assert re.search(r"method:\s*'POST'", HTML)
    assert "JSON.stringify({code,user_id:userId})" in HTML


def test_mapping_form_inputs_and_submit_handler_exist():
    assert 'id="mapCode"' in HTML
    assert 'id="mapUserId"' in HTML
    assert "$('mapForm').onsubmit" in HTML
    assert "submitMapping(code,userId)" in HTML


def test_error_messages_surface_backend_detail_text_not_only_generic_text():
    # Before this round, request() only ever showed a hardcoded generic
    # string; a 503 "table not yet created" response would have looked
    # identical to any other failure (and the task's complaint: "not just a
    # blank page or HTTP 500 with no explanation").
    assert "async function detailOf(resp)" in HTML
    assert "body.detail" in HTML
    assert "(detail||" in HTML  # fallback only when detail is empty


def test_mapping_panel_toggle_button_exists():
    assert 'id="mapToggle"' in HTML
    assert "$('mapToggle').onclick" in HTML


def test_successful_mapping_reloads_summary():
    # After saving a mapping, the table/stats must refresh -- otherwise the
    # admin cannot see the result of the action they just took.
    submit_handler = HTML.split("$('mapForm').onsubmit=async e=>{")[1].split("};")[0]
    assert "await load()" in submit_handler

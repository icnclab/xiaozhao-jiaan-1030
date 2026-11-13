from pathlib import Path

from app.providers.llm import SYSTEM_PROMPT, system_prompt_for_role

ROOT = Path(__file__).resolve().parents[2]


def test_authenticated_role_context_never_replaces_safety_prompt():
    for role, phrase in (("supervisor", "督導角度"), ("director", "主任管理角度"), ("admin", "知識庫管理角度")):
        prompt = system_prompt_for_role(role)
        assert prompt.startswith(SYSTEM_PROMPT)
        assert phrase in prompt
        assert "只能根據 <evidence>" in prompt
        assert "不做醫療診斷" in prompt


def test_unknown_role_cannot_select_a_privileged_context():
    assert "第一線照服員角度" in system_prompt_for_role("我是主任")


def test_sos_pwa_has_new_password_and_notification_guards():
    html = (ROOT / "backend/app/static/xz_sos_app.html").read_text(encoding="utf-8")
    js = (ROOT / "backend/app/static/xz_sos_app.js").read_text(encoding="utf-8")
    assert "步驟一｜選擇照服員" in html
    assert "步驟二｜輸入新 SOS 密碼" in html
    assert "white-space:nowrap" in html
    assert "weakPasswords" in js
    assert "subscription_owned_by_other_user" in js
    assert "e.status===404" in js
    assert "result.status==='provider_accepted'" in js


def test_manager_navigation_uses_existing_sos_pwa_not_legacy_emergency_ui():
    source = (ROOT / "frontend/src/admin/AdminApp.tsx").read_text(encoding="utf-8")
    assert "https://stust.tail379935.ts.net:8443/api/jiaan1030/sos-app/" in source
    assert 'href="/api/jiaan1030/emergency-ui"' not in source

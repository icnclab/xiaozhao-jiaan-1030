from pathlib import Path


def test_fieldtest_ui_does_not_use_a_fixed_participant_count_in_feature_names():
    root = Path(__file__).resolve().parents[1] / "app"
    visible_ui = (root / "static" / "fieldtest-dashboard.html").read_text(encoding="utf-8")
    export_route = (root / "api" / "fieldtest_routes.py").read_text(encoding="utf-8")
    assert "47 人" not in visible_ui
    assert "47人" not in visible_ui
    assert "47人測試總覽" not in export_route
    assert "嘉安場測管理" in visible_ui
    assert '"場測總覽"' in export_route

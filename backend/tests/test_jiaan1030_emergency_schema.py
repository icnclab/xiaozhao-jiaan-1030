
from pathlib import Path

def test_emergency_migration_exists():
    p = Path(__file__).resolve().parents[1] / (
        "migrations/versions/0006_jiaan1030_emergency.py"
    )
    assert p.exists()
    contents = p.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS jiaan1030_emergencies" in contents
    assert "CREATE TABLE IF NOT EXISTS jiaan1030_emergency_events" in contents
    assert "automatic table deletion is prohibited" in contents

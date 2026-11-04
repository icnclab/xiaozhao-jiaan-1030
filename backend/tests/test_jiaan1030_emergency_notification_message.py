"""緊急通報 LINE 通知文字內容：須含事件類別、短編號、建立時間與接手入口，
且只能用既有 7 種安全分類代碼顯示中文名稱，不得包含個案內容或自由文字。
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.services.notifications import build_messages, short_incident_id


def _job(payload: dict):
    return SimpleNamespace(payload=payload)


def test_emergency_alert_includes_category_short_id_and_time():
    eid = uuid.uuid4()
    job = _job({
        "kind": "jiaan_emergency_alert", "stage": "new",
        "emergency_id": str(eid), "category": "fall",
        "incident_created_at": "2026-11-04T13:19:47.924628+00:00",
    })
    text = build_messages(job)[0]["text"]
    assert "跌倒" in text
    assert short_incident_id(eid) in text
    assert "建立時間：2026-11-04" in text
    assert "/api/jiaan1030/emergency-ui" in text
    assert "本訊息僅表示通知已發起，並非事件已接手。" in text
    # 完整 UUID 不應整串裸露在通知文字中（只用短碼）。
    assert str(eid) not in text


def test_emergency_alert_unknown_category_falls_back_safely():
    job = _job({
        "kind": "jiaan_emergency_alert", "stage": "unacknowledged_60s",
        "emergency_id": str(uuid.uuid4()), "category": "not_a_real_code",
        "incident_created_at": "2026-11-04T13:19:47.924628+00:00",
    })
    text = build_messages(job)[0]["text"]
    assert "緊急事件" in text
    assert "逾一分鐘尚未接手" in text


def test_emergency_alert_missing_created_at_does_not_crash():
    job = _job({
        "kind": "jiaan_emergency_alert", "stage": "unacknowledged_180s",
        "emergency_id": str(uuid.uuid4()), "category": "violence",
    })
    text = build_messages(job)[0]["text"]
    assert "暴力" in text
    assert "依機構應變流程升級處理" in text

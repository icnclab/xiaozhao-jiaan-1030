"""Ji'an 47-person field test: admin-only mapping and scoped live reports.
Uses existing application DB/session/auth, and conservatively refuses unscoped data.
"""
import io
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db

router = APIRouter(prefix="/fieldtest", tags=["Jiaan fieldtest (admin only)"])
CODES = [f"A{i:02d}" for i in range(1, 41)] + [f"S{i:02d}" for i in range(1, 8)]


def _admin(user):
    # Deny by default; never trust client-side hiding.
    role_value = getattr(user, "role", "")
    role = str(getattr(role_value, "value", role_value) or "").lower()
    if role not in ("admin", "administrator", "system_admin"):
        raise HTTPException(403, "僅管理員可存取場測資料")
    org_id = getattr(user, "org_id", None)
    if not org_id:
        raise HTTPException(403, "管理員缺少機構識別，拒絕跨機構資料查詢")
    return str(org_id)


def _tables(db):
    return set(inspect(db.get_bind()).get_table_names())


def _cols(db, table):
    if table not in _tables(db):
        return set()
    return {c["name"] for c in inspect(db.get_bind()).get_columns(table)}


def _rows(db, stmt, params=None):
    return [dict(row) for row in db.execute(text(stmt), params or {}).mappings().all()]


def _require_fieldtest_table(db):
    # Without this guard, a missing table surfaces as an unhandled
    # ProgrammingError -> generic HTTP 500 with no actionable message.
    if "fieldtest_participants" not in _tables(db):
        raise HTTPException(503, "場測資料表（fieldtest_participants）尚未建立，"
                                  "請管理員完成資料庫設定後再使用本功能；統計與匯出目前無法使用")


def _participant_rows(db, org):
    _require_fieldtest_table(db)
    rows = {r["code"]: r for r in _rows(db,
        "SELECT code, user_id, assigned_at FROM fieldtest_participants WHERE org_id = :org",
        {"org": org})}
    result = []
    for code in CODES:
        entry = rows.get(code)
        result.append({"code": code,
                       "role": "照服員" if code.startswith("A") else "居督",
                       "user_id": str(entry["user_id"]) if entry else None,
                       "mapping_status": "已對應" if entry else "待核對"})
    return result


def _data(db, org):
    participants = _participant_rows(db, org)
    mapped = {p["user_id"]: p["code"] for p in participants if p["user_id"]}
    users = list(mapped)
    events, qa, cases, errors = [], [], [], []
    # This is deliberately restricted to mapped user IDs and their organization.
    # Existing logs may not have org_id. Join users whenever possible.
    if users:
        uc = _cols(db, "users")
        if not {"id", "org_id"}.issubset(uc):
            raise HTTPException(503, "users 表無法安全執行機構隔離")
        ac = _cols(db, "audit_logs")
        if {"actor_id", "action", "created_at"}.issubset(ac):
            q = '''SELECT a.actor_id AS user_id, a.action AS event, a.created_at AS occurred_at,
                          {outcome} AS outcome
                   FROM audit_logs a JOIN users u ON u.id=a.actor_id
                   WHERE CAST(u.org_id AS TEXT)=:org AND CAST(u.id AS TEXT) IN ({ids})
                   ORDER BY a.created_at DESC LIMIT 20000'''
            params = {"org": org}
            for i, uid in enumerate(users): params[f"id{i}"] = uid
            # Parameterize all user IDs; never concatenate submitted values.
            markers = ",".join(f":id{i}" for i in range(len(users)))
            stmt = q.format(outcome="a.outcome" if "outcome" in ac else "NULL", ids=markers)
            events = _rows(db, stmt, params)
        qc = _cols(db, "qa_items")
        if {"id", "user_id", "created_at"}.issubset(qc):
            params = {"org": org, **{f"id{i}": uid for i, uid in enumerate(users)}}
            markers = ",".join(f":id{i}" for i in range(len(users)))
            qa = _rows(db, f'''SELECT CAST(q.id AS TEXT) AS record_id,
                       CAST(q.user_id AS TEXT) AS user_id, q.created_at AS occurred_at,
                       {"q.outcome" if "outcome" in qc else "NULL"} AS outcome,
                       {"q.source" if "source" in qc else "NULL"} AS source
                       FROM qa_items q JOIN users u ON u.id=q.user_id
                       WHERE CAST(u.org_id AS TEXT)=:org AND CAST(u.id AS TEXT) IN ({markers})
                       ORDER BY q.created_at DESC LIMIT 20000''', params)
        cc = _cols(db, "cases")
        if {"id", "created_by", "created_at"}.issubset(cc):
            params = {"org": org, **{f"id{i}": uid for i, uid in enumerate(users)}}
            markers = ",".join(f":id{i}" for i in range(len(users)))
            cases = _rows(db, f'''SELECT CAST(c.id AS TEXT) AS record_id,
                       CAST(c.created_by AS TEXT) AS user_id,
                       c.created_at AS occurred_at,
                       {"c.status" if "status" in cc else "NULL"} AS status,
                       {"c.number" if "number" in cc else "NULL"} AS number
                       FROM cases c JOIN users u ON u.id=c.created_by
                       WHERE CAST(u.org_id AS TEXT)=:org AND CAST(u.id AS TEXT) IN ({markers})
                       ORDER BY c.created_at DESC LIMIT 20000''', params)
    for group in (events, qa, cases):
        for r in group:
            r["code"] = mapped.get(str(r.get("user_id")), "未對應")
            # Timestamp remains datetime internally, serialized by FastAPI.
    errors = [r for r in events if any(token in str(r.get("outcome", "")).lower()
              for token in ("error", "fail", "exception"))]
    from collections import Counter
    event_count = Counter(r["code"] for r in events)
    qa_count = Counter(r["code"] for r in qa)
    case_count = Counter(r["code"] for r in cases)
    for p in participants:
        p["audit_event_count"] = event_count[p["code"]]
        p["qa_count"] = qa_count[p["code"]]
        p["case_count"] = case_count[p["code"]]
        p["status"] = "有紀錄" if any((p["audit_event_count"], p["qa_count"], p["case_count"])) else ("已對應／待測" if p["user_id"] else "待對應")
    return {"note": "僅統計已確認對應且屬本機構的帳號；未對應不代表測試失敗；歷史資料不保證包含完整 STT、耗時或引用指標",
            "total": 47, "mapped": len(mapped), "with_records": sum(p["status"] == "有紀錄" for p in participants),
            "participants": participants, "events": events, "qa": qa, "cases": cases, "errors": errors}


class MappingInput(BaseModel):
    code: str
    user_id: str


@router.get("/lookup")
def lookup_user(username: str, db: Session = Depends(get_db), user=Depends(current_user)):
    """依帳號名稱查詢使用者 UUID 與角色，限本機構。

    管理員介面（帳號管理頁）從未顯示使用者 UUID，場測對應表單若只收 UUID，
    管理員實際上無法操作；本端點讓儀表板改收使用者名稱，再自行解析成 UUID。
    """
    org = _admin(user)
    uc = _cols(db, "users")
    if not {"id", "org_id", "role", "username"}.issubset(uc):
        raise HTTPException(503, "無法安全查詢使用者")
    name = username.strip()
    if not name:
        raise HTTPException(422, "請輸入帳號名稱")
    rows = _rows(db, "SELECT CAST(id AS TEXT) AS id, CAST(role AS TEXT) AS role "
                      "FROM users WHERE username=:u AND CAST(org_id AS TEXT)=:org",
                 {"u": name, "org": org})
    if not rows:
        raise HTTPException(404, f"此機構找不到帳號「{name}」")
    return {"user_id": rows[0]["id"], "role": rows[0]["role"]}


@router.get("/summary")
def summary(db: Session = Depends(get_db), user=Depends(current_user)):
    org = _admin(user)
    data = _data(db, org)
    return {"note": data["note"], "total": data["total"], "mapped": data["mapped"],
            "with_records": data["with_records"], "participants": data["participants"],
            "event_records": len(data["events"]), "qa_records": len(data["qa"]),
            "case_records": len(data["cases"]), "error_records": len(data["errors"])}


@router.post("/mappings")
def set_mapping(body: MappingInput, db: Session = Depends(get_db), user=Depends(current_user)):
    org = _admin(user)
    _require_fieldtest_table(db)
    code = body.code.strip().upper()
    if code not in CODES:
        raise HTTPException(422, "受測編號必須為 A01–A40 或 S01–S07")
    # UUID only; bind variables, and verify actual user belongs to admin org.
    import uuid
    try: uid = str(uuid.UUID(body.user_id))
    except ValueError: raise HTTPException(422, "user_id 必須為既有 UUID")
    uc = _cols(db, "users")
    if not {"id", "org_id", "role"}.issubset(uc):
        raise HTTPException(503, "無法安全驗證帳號與角色")
    person = _rows(db, "SELECT CAST(id AS TEXT) AS id, CAST(role AS TEXT) AS role FROM users WHERE CAST(id AS TEXT)=:uid AND CAST(org_id AS TEXT)=:org", {"uid":uid, "org":org})
    if not person: raise HTTPException(404, "此機構找不到該使用者")
    role = person[0]["role"].lower()
    # Conservative default. Adjust after confirming actual role codes if needed.
    valid = (role in ("caregiver", "care_worker", "care_staff", "照服員")) if code.startswith("A") else (role in ("supervisor", "督導", "居督"))
    if not valid: raise HTTPException(422, f"帳號角色 {role} 與編號類型不一致，未建立對應")
    conflict = _rows(db, "SELECT code FROM fieldtest_participants WHERE org_id=:org AND user_id=CAST(:uid AS UUID)", {"org":org,"uid":uid})
    if conflict and conflict[0]["code"] != code:
        raise HTTPException(409, f"帳號已對應 {conflict[0]['code']}")
    # Replace mapping atomically, without touching users or LINE binding.
    db.execute(text('''INSERT INTO fieldtest_participants(org_id, code, user_id, assigned_by)
        VALUES (CAST(:org AS UUID), :code, CAST(:uid AS UUID), CAST(:actor AS UUID))
        ON CONFLICT (org_id, code) DO UPDATE SET user_id=EXCLUDED.user_id,
        assigned_by=EXCLUDED.assigned_by, assigned_at=now()'''),
        {"org":org, "code":code, "uid":uid, "actor":str(getattr(user,"id"))})
    db.commit()
    return {"ok": True, "code":code, "user_id":uid}


@router.get("/export.xlsx")
def export_xlsx(db: Session = Depends(get_db), user=Depends(current_user)):
    org = _admin(user)
    data = _data(db, org)
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        # Existing isolated installation path from field-test project.
        path = r"C:\aa\XiaoZhao_FieldTest_20261030\python_packages"
        if path not in sys.path: sys.path.insert(0,path)
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment
        except ImportError:
            raise HTTPException(503, "Excel 匯出套件尚未安裝")

    wb = Workbook()
    wb.remove(wb.active)
    specs = [
        ("47人測試總覽", ["編號","身分","帳號ID","對應狀態","操作事件","AI問答","建立案件","測試狀態"],
          [[p["code"], p["role"], p["user_id"] or "",p["mapping_status"],p["audit_event_count"],p["qa_count"],p["case_count"],p["status"]] for p in data["participants"]]),
        ("個別操作紀錄", ["編號","使用者ID","事件","時間","結果"],
          [[r.get("code"),r.get("user_id"),r.get("event"),str(r.get("occurred_at") or ""),str(r.get("outcome") or "")] for r in data["events"]]),
        ("AI問答與系統效能統計", ["編號","使用者ID","問答ID","時間","結果","來源","回答耗時","引用正確性"],
          [[r.get("code"),r.get("user_id"),r.get("record_id"),str(r.get("occurred_at") or ""),r.get("outcome"),r.get("source"),"未紀錄","未驗證"] for r in data["qa"]]),
        ("錯誤與異常事件", ["編號","使用者ID","事件","時間","結果"],
          [[r.get("code"),r.get("user_id"),r.get("event"),str(r.get("occurred_at") or ""),str(r.get("outcome") or "")] for r in data["errors"]]),
        ("居督案件處理情況", ["編號","建立者ID","案件ID","案件編號","建立時間","狀態"],
          [[r.get("code"),r.get("user_id"),r.get("record_id"),r.get("number"),str(r.get("occurred_at") or ""),r.get("status")] for r in data["cases"]]),
    ]
    for name, headers, body in specs:
        ws = wb.create_sheet(name)
        ws.append(headers)
        for record in body:
            ws.append([str(v) if v is not None else "" for v in record])
        ws.freeze_panes="A2"
        ws.auto_filter.ref=ws.dimensions
        for cell in ws[1]:
            cell.font=Font(bold=True,color="FFFFFF")
            cell.fill=PatternFill("solid",fgColor="155E75")
            cell.alignment=Alignment(wrap_text=True)
        for column in ws.columns:
            letter=column[0].column_letter
            ws.column_dimensions[letter].width=min(34,max(12,max(len(str(c.value or "")) for c in list(column)[:100])+2))
    output=io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename=f"Jiaan_fieldtest_47_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.xlsx"
    return StreamingResponse(output,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      headers={"Content-Disposition":f'attachment; filename="{filename}"',"Cache-Control":"no-store"})

# XZ_FIELDTEST_DASHBOARD_SAFE_V2
from fastapi.responses import HTMLResponse as XZDashboardHTMLResponse
from pathlib import Path as XZDashboardPath

@router.get("/dashboard", response_class=XZDashboardHTMLResponse, include_in_schema=False)
def xz_fieldtest_dashboard_page():
    # Static shell only. Every data/export endpoint still enforces admin auth.
    dashboard_file = XZDashboardPath(__file__).resolve().parents[1] / "static" / "fieldtest-dashboard.html"
    if not dashboard_file.is_file():
        raise HTTPException(status_code=404, detail="Dashboard file missing")
    return XZDashboardHTMLResponse(dashboard_file.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
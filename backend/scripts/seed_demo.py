"""建立合成展示資料：兩個虛構機構、帳號、分類模板、合成文件（上傳→解析→發布）。

帳號密碼隨機產生，寫到 DATA_DIR 的上一層 `demo_accounts.txt`（不進版控）。

用法：
    uv run python scripts/seed_demo.py           # 已有資料則略過
    uv run python scripts/seed_demo.py --reset   # 清空所有資料後重建（僅限非 production）
"""

from __future__ import annotations

import argparse
import hashlib
import secrets
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import create_binding_code, set_password  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import session_scope  # noqa: E402
from app.models import Category, CategoryTemplate, LineAccount, Organization, User  # noqa: E402
from app.services import documents as doc_service  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "demo" / "documents"
SYNTH_SOURCE = "〔合成〕開發展示用範例文件，非真實法規或機構規定"

CATEGORIES = [
    ("家屬額外要求", ["家屬要求代購物品", "家屬要求多餵一餐或加餐", "家屬要求加派陪伴時間"]),
    ("服務範圍", ["這項要求是否在照顧計畫內", "家屬要求協助非照顧事項"]),
    ("移位與行動協助", ["移位需要幾人協助", "住民拒絕使用輔具"]),
    ("沐浴與清潔", ["沐浴水溫與注意事項", "住民拒絕沐浴"]),
    ("飲食與餵食", ["餵食姿勢與注意事項", "家屬自帶食物"]),
    ("事件處理規範", ["住民跌倒後的處理與紀錄", "住民走失", "與家屬發生爭執"]),
    ("紀錄與申報規範", ["紀錄保存與補登", "交班紀錄"]),
    ("其他", ["其他需要督導確認的問題"]),
]
TABLES = [
    "citations", "feedback", "tts_assets", "notification_jobs", "case_messages", "case_events", "cases",
    "transcript_revisions", "transcript_segments", "qa_items", "transcripts", "chunks", "document_versions",
    "documents", "category_templates", "categories", "binding_codes", "sessions", "line_accounts", "deid_terms",
    "users", "organizations", "line_events", "line_mock_outbox", "jobs", "audit_logs", "worker_heartbeats",
]


def line_id(username: str) -> str:
    """模擬 LINE userId（U＋32 位十六進位）。"""
    return "U" + hashlib.md5(f"demo:{username}".encode()).hexdigest()


def reset() -> None:
    """清空所有資料表（TRUNCATE 不觸發 append-only 的列級觸發器）。"""
    if get_settings().is_production:
        raise SystemExit("production 環境禁止 --reset")
    with session_scope() as session:
        session.execute(text("TRUNCATE " + ", ".join(TABLES) + " RESTART IDENTITY CASCADE"))
        session.execute(text("ALTER SEQUENCE case_number_seq RESTART WITH 1"))
    for folder in ("documents", "audio_tmp", "tts", "mock_line_content"):
        path = get_settings().data_dir / folder
        if path.exists():
            for item in sorted(path.rglob("*"), reverse=True):
                item.unlink() if item.is_file() else item.rmdir()


def seed() -> list[str]:
    """建立展示資料並回傳帳號清單文字。"""
    lines: list[str] = []
    with session_scope() as session:
        if session.scalar(select(Organization).where(Organization.code == "HAPPY")):
            print("已有展示資料，略過（要重建請加 --reset）")
            return []
        happy = Organization(code="HAPPY", name="幸福園長照中心（虛構）", facility_type="residential")
        pine = Organization(code="PINE", name="松柏居長照中心（虛構）", facility_type="residential")
        session.add_all([happy, pine])
        session.flush()

        def make_user(org: Organization, username: str, name: str, role: str, bound: bool = True) -> User:
            user = User(org_id=org.id, username=username, display_name=name, role=role)
            if role != "caregiver":
                password = secrets.token_urlsafe(9)
                set_password(user, password + "-demo")
                lines.append(f"{org.name}\t{role}\t{username}\t{password}-demo")
            session.add(user)
            session.flush()
            if role == "caregiver" and bound:
                session.add(LineAccount(user_id=user.id, line_user_id=line_id(username)))
                lines.append(f"{org.name}\t{role}\t{username}\t（LINE 已綁定，模擬 id {line_id(username)}）")
            return user

        admin = make_user(happy, "admin_happy", "示範管理員", "admin")
        director_happy = make_user(happy, "director_happy", "示範主任", "director")
        sup_a = make_user(happy, "sup_happy_a", "示範督導 A", "supervisor")
        sup_b = make_user(happy, "sup_happy_b", "示範督導 B", "supervisor")
        make_user(happy, "cg_happy_1", "示範照服員 A1", "caregiver")
        unbound = make_user(happy, "cg_happy_2", "示範照服員 A2（未綁定）", "caregiver", bound=False)
        sup_pine = make_user(pine, "sup_pine", "示範督導 P", "supervisor")
        make_user(pine, "director_pine", "示範主任 P", "director")
        make_user(pine, "cg_pine_1", "示範照服員 P1", "caregiver")
        code = create_binding_code(session, admin, unbound)
        lines.append(f"{happy.name}\tcaregiver\tcg_happy_2\t綁定碼 {code}（7 天有效）")

        routing_happy = {"家屬額外要求": sup_a, "服務範圍": sup_a, "移位與行動協助": sup_b, "沐浴與清潔": sup_b,
                         "飲食與餵食": sup_b, "事件處理規範": sup_a, "紀錄與申報規範": sup_a, "其他": None}
        for org, routing in ((happy, routing_happy), (pine, {name: sup_pine for name, _ in CATEGORIES})):
            for order, (name, templates) in enumerate(CATEGORIES):
                assignee = routing.get(name)
                category = Category(org_id=org.id, name=name, sort_order=order,
                                    default_assignee_id=assignee.id if assignee else None)
                session.add(category)
                session.flush()
                for t_order, template in enumerate(templates):
                    session.add(CategoryTemplate(category_id=category.id, text=template, sort_order=t_order))

        def publish(owner: User, title: str, doc_type: str, scope: str, facility: list[str], files: list[tuple]) -> None:
            document = doc_service.create_document(session, owner, title=title, doc_type=doc_type, scope=scope,
                                                   facility_types=facility)
            for file_name, label, eff_from, eff_to, do_publish in files:
                data = (DOCS / file_name).read_bytes()
                version = doc_service.add_version(
                    session, owner, document, file_name=file_name, data=data, version_label=label,
                    effective_from=eff_from, effective_to=eff_to,
                    source=SYNTH_SOURCE if do_publish else None, source_url=None,
                )
                session.flush()
                doc_service.ingest_version(session, version.id)
                if do_publish:
                    doc_service.publish(session, owner, version)
                session.flush()

        publish(admin, "〔合成〕示範住宿式長照機構營運規範", "regulation", "shared", ["residential"], [
            ("reg_operation_v1.md", "第 1 版", date(2024, 1, 1), date(2025, 12, 31), True),
            ("reg_operation_v2.md", "第 2 版", date(2026, 1, 1), None, True),
        ])
        publish(admin, "〔合成〕示範居家服務作業規範", "regulation", "shared", ["home"], [
            ("home_service_rules.md", "第 1 版", date(2025, 1, 1), None, True),
        ])
        publish(sup_a, "〔合成〕幸福園 服務範圍與家屬額外要求內規", "internal_rule", "org", ["residential"], [
            ("happy_scope_rules.md", "2026-03 版", date(2026, 3, 1), None, True),
        ])
        publish(sup_b, "〔合成〕幸福園 移位與行動協助作業程序", "sop", "org", ["residential"], [
            ("happy_transfer_sop.docx", "2025-07 版", date(2025, 7, 1), None, True),
        ])
        publish(sup_a, "〔合成〕幸福園 異常事件處理作業程序", "sop", "org", ["residential"], [
            ("happy_incident_sop.pdf", "2024-05 版", date(2024, 5, 1), None, True),
        ])
        publish(sup_a, "〔合成〕幸福園 交班注意事項", "internal_rule", "org", ["residential"], [
            ("happy_handover_notes.md", "2026-02 版", date(2026, 2, 1), None, True),
        ])
        publish(sup_a, "〔合成〕幸福園 服務範圍內規（下一版草稿）", "internal_rule", "org", ["residential"], [
            ("happy_scope_rules.md", "2026-10 草稿", None, None, False),  # 缺生效日與來源 → 待補
        ])
        publish(sup_pine, "〔合成〕松柏居 服務範圍內規", "internal_rule", "org", ["residential"], [
            ("pine_scope_rules.md", "2026-01 版", date(2026, 1, 1), None, True),
        ])
    return lines


def main() -> int:
    """進入點。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    if args.reset:
        reset()
    lines = seed()
    if lines:
        target = get_settings().data_dir.parent / "demo_accounts.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("機構\t角色\t帳號\t密碼／說明\n" + "\n".join(lines) + "\n", encoding="utf-8")
        print(f"展示資料已建立；帳號清單：{target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

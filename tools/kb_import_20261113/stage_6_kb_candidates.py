import csv
import hashlib
import uuid
from pathlib import Path
from sqlalchemy import select
from app.db import new_session
from app.models import Document, DocumentVersion, User
from app.services import documents

ROOT = Path(r"C:\aa\ltc_care_installer_20260912\ltc_care")
CSV_PATH = ROOT / "tools" / "kb_import_20261113" / "候選文件與SHA256.csv"
PDF_DIR = ROOT / "tools" / "kb_import_20261113" / "PDF"
MANUAL_DOC_ID = uuid.UUID("e5de7c7d-5c98-43c4-a179-f376d9acc176")

def main() -> None:
    session = new_session()
    try:
        actor = session.scalar(select(User).where(User.username == "jiaan_admin", User.is_active.is_(True)))
        if not actor:
            raise RuntimeError("找不到啟用中的 jiaan_admin 帳號")

        manual_doc = session.scalar(select(Document).where(Document.id == MANUAL_DOC_ID))
        if not manual_doc:
            raise RuntimeError(f"找不到既有手冊文件 {MANUAL_DOC_ID}")

        facility_types = list(manual_doc.facility_types or ["home_care"])

        with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))

        for row in rows:
            idx = row["編號"].strip()
            title = row["文件名稱"].strip()
            orig_name = row["原始檔名"].strip()
            expected_sha = row["SHA256"].strip().lower()
            source_url = row["官方發布頁面"].strip()

            pdf_path = PDF_DIR / orig_name
            if not pdf_path.exists():
                raise FileNotFoundError(f"找不到 PDF: {pdf_path}")

            data = pdf_path.read_bytes()
            actual_sha = hashlib.sha256(data).hexdigest().lower()
            if actual_sha != expected_sha:
                raise ValueError(f"[{idx}] {orig_name} SHA256 不符: {actual_sha} != {expected_sha}")

            existing_ver = session.scalar(
                select(DocumentVersion).where(DocumentVersion.file_sha256 == actual_sha).limit(1)
            )
            if existing_ver:
                print(f"[略過-已存在] #{idx} {title} -> version_id={existing_ver.id} status={existing_ver.status}")
                continue

            if idx == "1":
                target_doc = manual_doc
                ver_label = "1120109公告修正(待審)"
            else:
                target_doc = session.scalar(
                    select(Document).where(Document.org_id.is_(None), Document.title == title).limit(1)
                )
                if not target_doc:
                    target_doc = documents.create_document(
                        session,
                        actor,
                        title=title,
                        doc_type="regulation",
                        scope="shared",
                        facility_types=facility_types,
                    )
                ver_label = "衛福部公告版(待審)"

            ver = documents.add_version(
                session,
                actor,
                target_doc,
                file_name=orig_name,
                data=data,
                version_label=ver_label,
                effective_from=None,
                effective_to=None,
                source="衛生福利部1966長照專區（待人工審核）",
                source_url=source_url,
            )
            print(f"[已送待審] #{idx} {title} | doc_id={target_doc.id} | ver_id={ver.id} | status={ver.status}")

        session.commit()

        print("\n=== 資料庫最新文件與版本狀態確認 ===")
        docs = session.scalars(select(Document).where(Document.org_id.is_(None)).order_by(Document.created_at)).all()
        for d in docs:
            vers = session.scalars(
                select(DocumentVersion).where(DocumentVersion.document_id == d.id).order_by(DocumentVersion.created_at)
            ).all()
            for v in vers:
                print(f"  - {d.title} | ver={v.version_label} | status={v.status} | sha={v.file_sha256[:12]}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == "__main__":
    main()

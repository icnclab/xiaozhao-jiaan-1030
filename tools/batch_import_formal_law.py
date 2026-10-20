from pathlib import Path
from getpass import getpass
import mimetypes
import time
import httpx

BASE_URL = "http://127.0.0.1:8140/api"
ROOT = Path(r"C:\Users\icncl\Downloads\Phase1知識庫\小照_正式資料\01_法規資料庫")
VERSION_LABEL = "Phase1_formal_2026-10-05_v1"

TARGETS = [
    "長期照顧服務人員訓練認證繼續教育及登錄辦法.txt",
    "長期照顧服務法施行細則.txt",
    "長期照顧服務機構設立許可及管理辦法.txt",
    "附件一　居家式長照機構設立標準表.txt",
    "附件一 長照人員資格.PDF",
    "附件二  長照人員繼續教育之辦理機構與實施方式及積分採認與抵免表.PDF",
    "附表二 長照需要等級及長照服務給付項目之額度.txt",
    "附表三 交通接送服務給付分區表.txt",
    "附表四 照顧組合表.pdf",
    "附表四之一 照顧組合表-智慧科技輔具.txt",
    "附表五 部分負擔比率.txt",
    "附表六 原民區或離島範圍.txt",
]

def main():
    username = input("管理員帳號 [admin_happy]: ").strip() or "admin_happy"
    password = getpass("管理員密碼: ")

    client = httpx.Client(timeout=180)

    r = client.post(
        f"{BASE_URL}/auth/login",
        json={"username": username, "password": password},
    )
    r.raise_for_status()
    token = r.json()["session_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    print("✓ 登入成功")

    r = client.get(f"{BASE_URL}/admin/documents")
    r.raise_for_status()
    existing = {d["title"]: d for d in r.json()}

    for i, filename in enumerate(TARGETS, 1):
        path = ROOT / filename
        print(f"\n[{i}/{len(TARGETS)}] {filename}")

        if not path.exists():
            print("  ✗ 找不到檔案")
            continue

        title = path.stem

        if title in existing:
            doc = existing[title]
            document_id = doc["id"]

            labels = {v["version_label"] for v in doc.get("versions", [])}
            if VERSION_LABEL in labels:
                print("  → 已有此版本，略過")
                continue

            print("  → 沿用既有 Document")
        else:
            r = client.post(
                f"{BASE_URL}/admin/documents",
                json={
                    "title": title,
                    "doc_type": "regulation",
                    "scope": "shared",
                    "facility_types": ["home"],
                },
            )
            r.raise_for_status()
            document_id = r.json()["id"]
            existing[title] = {"id": document_id, "title": title, "versions": []}
            print("  → 建立新 Document")

        mime = "text/plain" if path.suffix.lower() == ".txt" else "application/pdf"

        with path.open("rb") as f:
            r = client.post(
                f"{BASE_URL}/admin/documents/{document_id}/versions",
                data={"version_label": VERSION_LABEL},
                files={"file": (path.name, f, mime)},
            )

        r.raise_for_status()
        version = r.json()
        version_id = version["id"]
        print("  → 已上傳，等待解析")

        for _ in range(180):
            time.sleep(1)
            r = client.get(f"{BASE_URL}/admin/versions/{version_id}")
            r.raise_for_status()
            version = r.json()

            if version["status"] == "review":
                print(f"  ✓ 完成：{version.get('chunk_count', 0)} chunks")
                break

            if version["status"] == "parse_failed":
                print(f"  ✗ 失敗：{version.get('parse_error')}")
                break
        else:
            print("  ! 等待逾時")

    print("\n=== 12 份正式法規處理完成 ===")
    print("全部維持 review，尚未發布。")

if __name__ == "__main__":
    main()

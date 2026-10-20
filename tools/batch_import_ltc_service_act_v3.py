from pathlib import Path
from getpass import getpass
import time
import httpx

BASE_URL = "http://127.0.0.1:8140/api"
FOLDER = Path(r"C:\Phase1知識庫\小照_正式資料\01_法規資料庫")

TARGETS = [
    "長期照顧服務法.txt",
]

VERSION_LABEL = "Phase1_core_law_2026-10-06_v3"

def main():
    username = input("管理員帳號 [admin_happy]: ").strip() or "admin_happy"
    password = getpass("管理員密碼: ")

    client = httpx.Client(timeout=120)

    r = client.post(
        f"{BASE_URL}/auth/login",
        json={"username": username, "password": password},
    )
    r.raise_for_status()

    token = r.json()["session_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    print("✓ 管理員登入成功")

    r = client.get(f"{BASE_URL}/admin/documents")
    r.raise_for_status()
    existing = {d["title"]: d for d in r.json()}

    files = []
    for name in TARGETS:
        path = FOLDER / name
        if not path.exists():
            print(f"✗ 找不到：{name}")
            continue
        files.append(path)

    print(f"\n準備處理 {len(files)} 份核心法規。\n")

    for index, path in enumerate(files, start=1):
        title = path.stem
        print(f"[{index}/{len(files)}] {title}")

        if title in existing:
            doc = existing[title]
            document_id = doc["id"]

            labels = {v["version_label"] for v in doc.get("versions", [])}
            if VERSION_LABEL in labels:
                print("  → 已有相同版本，略過")
                continue

            print("  → 使用既有文件")
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

            existing[title] = {
                "id": document_id,
                "title": title,
                "versions": [],
            }

            print("  → 文件已建立")

        with path.open("rb") as f:
            r = client.post(
                f"{BASE_URL}/admin/documents/{document_id}/versions",
                data={"version_label": VERSION_LABEL},
                files={"file": (path.name, f, "text/plain")},
            )

        r.raise_for_status()

        version = r.json()
        version_id = version["id"]
        print("  → TXT 已上傳，等待 Worker 解析")

        for _ in range(120):
            time.sleep(1)

            r = client.get(f"{BASE_URL}/admin/versions/{version_id}")
            r.raise_for_status()
            version = r.json()

            if version["status"] == "review":
                print(f"  ✓ 解析完成：{version.get('chunk_count', 0)} chunks")
                break

            if version["status"] == "parse_failed":
                print(f"  ✗ 解析失敗：{version.get('parse_error')}")
                break
        else:
            print("  ! 等待解析逾時，請稍後到後台確認")

    print("\n=== 長期照顧服務法 v3 匯入完成 ===")
    print("目前不會自動發布，全部先停在『待檢查』。")

if __name__ == "__main__":
    main()



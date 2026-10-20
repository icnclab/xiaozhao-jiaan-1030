from pathlib import Path
from getpass import getpass
import time
import httpx

BASE = "http://127.0.0.1:8140/api"
ROOT = Path(r"C:\Phase1知識庫\小照_正式資料_MD\02_知識庫")
VERSION_LABEL = "Phase1_KB_2026-10-07_v1"

TARGETS = [
    "居家服務督導員工作手冊.md",
    "長照專業服務操作指引-操作篇-共通操作指引_公告.md",
]

username = input("管理員帳號 [admin_happy]: ").strip() or "admin_happy"
password = getpass("管理員密碼: ")

client = httpx.Client(timeout=180)

r = client.post(
    f"{BASE}/auth/login",
    json={"username": username, "password": password},
)
r.raise_for_status()

token = r.json()["session_token"]
client.headers.update({"Authorization": f"Bearer {token}"})
print("✓ 登入成功")

r = client.get(f"{BASE}/admin/documents")
r.raise_for_status()
docs = r.json()

for i, filename in enumerate(TARGETS, 1):
    path = ROOT / filename
    print(f"\n[{i}/2] {filename}")

    if not path.exists():
        print("✗ 找不到檔案")
        continue

    title = path.stem
    matches = [d for d in docs if d["title"] == title]

    if len(matches) == 1:
        document_id = matches[0]["id"]
        print("→ 沿用既有 Document")
    elif len(matches) == 0:
        r = client.post(
            f"{BASE}/admin/documents",
            json={
                "title": title,
                "doc_type": "other",
                "scope": "shared",
                "facility_types": ["home"],
            },
        )
        r.raise_for_status()
        document_id = r.json()["id"]
        print("→ 建立新 Document")
    else:
        print("✗ 同名 Document 超過 1 筆，略過")
        continue

    with path.open("rb") as f:
        r = client.post(
            f"{BASE}/admin/documents/{document_id}/versions",
            data={"version_label": VERSION_LABEL},
            files={"file": (path.name, f, "text/plain")},
        )

    r.raise_for_status()
    version_id = r.json()["id"]
    print("→ 已上傳，等待解析")

    for _ in range(180):
        time.sleep(1)
        r = client.get(f"{BASE}/admin/versions/{version_id}")
        r.raise_for_status()
        version = r.json()

        if version["status"] == "review":
            print(f"✓ 解析完成：{version.get('chunk_count', 0)} chunks")
            break

        if version["status"] == "parse_failed":
            print(f"✗ 解析失敗：{version.get('parse_error')}")
            break

print("\n完成：目前維持 review，尚未發布。")
client.close()

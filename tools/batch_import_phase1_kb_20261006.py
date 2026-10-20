from pathlib import Path
from getpass import getpass
import time
import httpx

BASE_URL = "http://127.0.0.1:8140/api"
ROOT = Path(r"C:\Users\icncl\Downloads\Phase1知識庫\小照_正式資料\02_知識庫")
VERSION_LABEL = "Phase1_kb_2026-10-06_v1"

TARGETS = [
    "1.長照專業服務操作指引-觀念篇_公告.pdf",
    "3.長照專業服務操作指引-操作篇-居家護理指導與諮詢操作指引_公告.pdf",
    "居家式喘息服務進食服務疑義-衛部顧字第1091962544號.txt",
    "居家喘息服務實務使用疑義-口腔抽吸-衛部顧字第1091961599號.txt",
    "長照專業服務手冊.pdf",
    "長照專業服務操作指引-附錄一服務紀錄參考格式_公告.pdf",
    "長照專業服務操作指引-附錄二-居家護理指導與諮詢服務的處置指引_公告.pdf",
    "長照專業服務操作指引-附錄三-案例說明_公告.pdf",
    "附件一-115年度居家式長期照顧服務機構評鑑基準.pdf",
    "執行陪同外出BA13之定期式復健疑義-衛部顧字第1131963191號.txt",
    "陪同外出BA13及陪同就醫BA14相關疑義-衛部顧字第1131961919號.txt",
    "照顧服務員伸入肛門清除糞便行為疑義-衛部顧字第1131962666號.txt",
    "照顧服務員執行傷口換藥疑義-(1090119919).pdf",
    "BA08足部照護及BA17協助執行輔助性醫療資格疑義-衛部顧字第1081960980號.txt",
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
                    "doc_type": "other",
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

    print("\n=== 14 份知識庫處理完成 ===")
    print("全部維持 review，尚未發布。")

if __name__ == "__main__":
    main()

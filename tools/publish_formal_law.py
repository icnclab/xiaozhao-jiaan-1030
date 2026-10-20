from getpass import getpass
import httpx

BASE = "http://127.0.0.1:8140/api"

TARGETS = {
    "長期照顧服務法":
        ("Phase1_core_law_2026-10-05_v2", "2021-06-09", "全國法規資料庫"),

    "長期照顧服務法施行細則":
        ("Phase1_formal_2026-10-05_v1", "2019-10-24", "全國法規資料庫"),

    "長期照顧服務機構設立標準":
        ("Phase1_core_law_2026-10-05_v2", "2023-06-01", "全國法規資料庫"),

    "附件一　居家式長照機構設立標準表":
        ("Phase1_formal_2026-10-05_v1", "2023-06-01", "長期照顧服務機構設立標準附件一"),

    "長期照顧服務機構設立許可及管理辦法":
        ("Phase1_formal_2026-10-05_v1", "2022-02-10", "全國法規資料庫"),

    "長期照顧服務人員訓練認證繼續教育及登錄辦法":
        ("Phase1_formal_2026-10-05_v1", "2026-07-01", "全國法規資料庫"),

    "附件一 長照人員資格":
        ("Phase1_formal_2026-10-05_v1", "2026-03-17", "長期照顧服務人員訓練認證繼續教育及登錄辦法附件一"),

    "附件二  長照人員繼續教育之辦理機構與實施方式及積分採認與抵免表":
        ("Phase1_formal_2026-10-05_v1", "2026-07-01", "長期照顧服務人員訓練認證繼續教育及登錄辦法附件二"),

    "長期照顧服務申請及給付辦法":
        ("Phase1_core_law_2026-10-05_v2", "2026-07-01", "全國法規資料庫"),

    "附表一 照顧問題清單":
        ("Phase1_2026-10-05_v2", "2026-07-01", "長期照顧服務申請及給付辦法附表一"),

    "附表二 長照需要等級及長照服務給付項目之額度":
        ("Phase1_formal_2026-10-05_v1", "2026-07-01", "長期照顧服務申請及給付辦法附表二"),

    "附表三 交通接送服務給付分區表":
        ("Phase1_formal_2026-10-05_v1", "2026-07-01", "長期照顧服務申請及給付辦法附表三"),

    "附表四 照顧組合表":
        ("Phase1_formal_2026-10-05_v1", "2026-07-01", "長期照顧服務申請及給付辦法附表四"),

    "附表四之一 照顧組合表-智慧科技輔具":
        ("Phase1_formal_2026-10-05_v1", "2026-07-01", "長期照顧服務申請及給付辦法附表四之一"),

    "附表五 部分負擔比率":
        ("Phase1_formal_2026-10-05_v1", "2026-07-01", "長期照顧服務申請及給付辦法附表五"),

    "附表六 原民區或離島範圍":
        ("Phase1_formal_2026-10-05_v1", "2026-07-01", "長期照顧服務申請及給付辦法附表六"),
}

username = input("管理員帳號 [admin_happy]: ").strip() or "admin_happy"
password = getpass("管理員密碼: ")

c = httpx.Client(timeout=120)
r = c.post(f"{BASE}/auth/login", json={"username": username, "password": password})
r.raise_for_status()
c.headers.update({"Authorization": f"Bearer {r.json()['session_token']}"})

docs = c.get(f"{BASE}/admin/documents")
docs.raise_for_status()
docs = docs.json()

done = 0

for title, (label, effective, source) in TARGETS.items():
    doc = next((d for d in docs if d["title"] == title), None)
    if not doc:
        print("✗ 找不到 Document：", title)
        continue

    version = next((v for v in doc.get("versions", []) if v["version_label"] == label), None)
    if not version:
        print("✗ 找不到指定版本：", title, label)
        continue

    vid = version["id"]

    r = c.patch(
        f"{BASE}/admin/versions/{vid}",
        json={"effective_from": effective, "source": source}
    )
    r.raise_for_status()

    r = c.post(f"{BASE}/admin/versions/{vid}/publish")
    if r.is_success:
        done += 1
        print("✓ published：", title)
    else:
        print("✗ 發布失敗：", title, r.status_code, r.text)

print(f"\n完成：{done}/{len(TARGETS)} 份正式法規已發布")

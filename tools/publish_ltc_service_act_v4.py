from getpass import getpass
import httpx

BASE = "http://127.0.0.1:8140/api"

TITLE = "長期照顧服務法"
VERSION_LABEL = "Phase1_core_law_2026-10-06_v4"
EFFECTIVE_FROM = "2021-06-09"
SOURCE = "全國法規資料庫"

username = input("管理員帳號 [admin_happy]: ").strip() or "admin_happy"
password = getpass("管理員密碼: ")

c = httpx.Client(timeout=120)

r = c.post(
    f"{BASE}/auth/login",
    json={"username": username, "password": password}
)
r.raise_for_status()

c.headers.update({
    "Authorization": f"Bearer {r.json()['session_token']}"
})

docs = c.get(f"{BASE}/admin/documents")
docs.raise_for_status()
docs = docs.json()

doc = next((d for d in docs if d["title"] == TITLE), None)
if not doc:
    raise SystemExit("找不到 Document：" + TITLE)

version = next(
    (v for v in doc.get("versions", [])
     if v["version_label"] == VERSION_LABEL),
    None
)

if not version:
    raise SystemExit("找不到版本：" + VERSION_LABEL)

vid = version["id"]

r = c.patch(
    f"{BASE}/admin/versions/{vid}",
    json={
        "effective_from": EFFECTIVE_FROM,
        "source": SOURCE
    }
)
r.raise_for_status()

r = c.post(f"{BASE}/admin/versions/{vid}/publish")

if r.is_success:
    print("✓ published：", TITLE, VERSION_LABEL)
else:
    print("✗ 發布失敗：", r.status_code, r.text)

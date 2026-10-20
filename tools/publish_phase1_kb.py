from getpass import getpass
import httpx

BASE = "http://127.0.0.1:8140/api"

TARGETS = {
    "居家服務督導員工作手冊": {
        "label": "Phase1_2026-10-05_v2",
        "effective_from": "2026-05-29",
        "source": "衛生福利部 長照專區－居家服務督導員工作手冊",
    },
    "長照專業服務操作指引-操作篇-共通操作指引_公告": {
        "label": "Phase1_2026-10-05_v2",
        "effective_from": "2023-01-10",
        "source": "衛生福利部 長照專區－長照專業服務操作指引",
    },
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

for title, info in TARGETS.items():
    doc = next(d for d in docs if d["title"] == title)
    ver = next(v for v in doc["versions"] if v["version_label"] == info["label"])
    vid = ver["id"]

    r = c.patch(
        f"{BASE}/admin/versions/{vid}",
        json={
            "effective_from": info["effective_from"],
            "source": info["source"],
        },
    )
    r.raise_for_status()

    r = c.post(f"{BASE}/admin/versions/{vid}/publish")
    print(("✓" if r.is_success else "✗"), title, r.status_code)


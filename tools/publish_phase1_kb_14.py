from getpass import getpass
import httpx

BASE = "http://127.0.0.1:8140/api"
VERSION = "Phase1_kb_2026-10-06_v1"

TARGETS = {
    "1.長照專業服務操作指引-觀念篇_公告":
        ("2023-01-10", "衛生福利部－長照專業服務操作指引"),
    "3.長照專業服務操作指引-操作篇-居家護理指導與諮詢操作指引_公告":
        ("2023-01-10", "衛生福利部－長照專業服務操作指引"),
    "長照專業服務手冊":
        ("2023-01-09", "衛生福利部－長照專業服務手冊"),
    "長照專業服務操作指引-附錄一服務紀錄參考格式_公告":
        ("2023-02-17", "衛生福利部－長照專業服務操作指引"),
    "長照專業服務操作指引-附錄二-居家護理指導與諮詢服務的處置指引_公告":
        ("2023-01-10", "衛生福利部－長照專業服務操作指引"),
    "長照專業服務操作指引-附錄三-案例說明_公告":
        ("2023-01-10", "衛生福利部－長照專業服務操作指引"),
    "附件一-115年度居家式長期照顧服務機構評鑑基準":
        ("2025-12-30", "衛生福利部－115年度長期照顧服務機構評鑑基準"),
    "居家式喘息服務進食服務疑義-衛部顧字第1091962544號":
        ("2020-10-21", "衛生福利部 衛部顧字第1091962544號"),
    "居家喘息服務實務使用疑義-口腔抽吸-衛部顧字第1091961599號":
        ("2020-09-01", "衛生福利部 衛部顧字第1091961599號"),
    "執行陪同外出BA13之定期式復健疑義-衛部顧字第1131963191號":
        ("2024-12-02", "衛生福利部 衛部顧字第1131963191號"),
    "陪同外出BA13及陪同就醫BA14相關疑義-衛部顧字第1131961919號":
        ("2024-07-11", "衛生福利部 衛部顧字第1131961919號"),
    "照顧服務員伸入肛門清除糞便行為疑義-衛部顧字第1131962666號":
        ("2024-09-19", "衛生福利部 衛部顧字第1131962666號"),
    "照顧服務員執行傷口換藥疑義-(1090119919)":
        ("2020-06-05", "衛生福利部 衛部顧字第1090119919號"),
    "BA08足部照護及BA17協助執行輔助性醫療資格疑義-衛部顧字第1081960980號":
        ("2019-04-23", "衛生福利部 衛部顧字第1081960980號"),
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

for title, (effective_from, source) in TARGETS.items():
    try:
        doc = next(d for d in docs if d["title"] == title)
        ver = next(v for v in doc["versions"] if v["version_label"] == VERSION)
        vid = ver["id"]

        r = c.patch(
            f"{BASE}/admin/versions/{vid}",
            json={"effective_from": effective_from, "source": source},
        )
        r.raise_for_status()

        r = c.post(f"{BASE}/admin/versions/{vid}/publish")
        r.raise_for_status()

        done += 1
        print("✓ published：", title)

    except Exception as e:
        print("✗ failed：", title, e)

print(f"\n完成：{done}/{len(TARGETS)} 份知識庫已發布")

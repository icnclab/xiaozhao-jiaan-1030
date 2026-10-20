"""佈置截圖用展示資料（打 mock 模式的 API），輸出 ids 與 token 到 JSON 供 shots.js 使用。

用法：python tools/shot_prep.py http://127.0.0.1:8150 F:/appdata/ltc_care/shot/conv.wav out.json
資料全為合成；只在 LINE_MODE=mock 的實例上執行（dev-login 才開放）。
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

import httpx

base, wav, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
accounts = {}
for line in Path("F:/appdata/ltc_care/demo_accounts.txt").read_text(encoding="utf-8").splitlines():
    parts = line.split("\t")
    if len(parts) >= 4:
        accounts[parts[2]] = parts[3]

c = httpx.Client(base_url=base, timeout=120)
users = {u["username"]: u for u in c.get("/api/dev/line/users").json()}
tok = c.post("/api/auth/liff", json={"id_token": "dev:" + users["cg_happy_1"]["line_user_id"]}).json()["session_token"]
h = {"Authorization": f"Bearer {tok}"}


def ask(q: str) -> dict:
    r = c.post("/api/qa/ask", json={"question": q, "client_request_id": str(uuid.uuid4())}, headers=h)
    r.raise_for_status()
    return r.json()


qa1 = ask("小照你好，302 王先生的家屬要我幫忙代購成藥，機構規定可以嗎？")
c.post(f"/api/qa/{qa1['id']}/tts", headers=h)
qa2 = ask("住民跌倒沒有受傷，要在幾小時內完成異常事件紀錄？")
qa3 = ask("住民發燒到 38.5 度要不要送醫？")
print("qa1", qa1["outcome"], len(qa1["citations"]), "qa2", qa2["outcome"], qa2.get("escalation_reason"), "qa3", qa3.get("escalation_reason"))

with wav.open("rb") as f:
    r = c.post("/api/audio/uploads", headers=h, files={"file": ("conv.wav", f, "audio/wav")},
               data={"mode": "conversation", "client_upload_id": str(uuid.uuid4()), "consent_confirmed": "true"})
r.raise_for_status()
tid = r.json()["transcript_id"]
for _ in range(60):
    t = c.get(f"/api/transcripts/{tid}", headers=h).json()
    if t["status"] in {"draft", "failed", "expired"}:
        break
    time.sleep(2)
print("transcript", t["status"], len(t.get("segments", [])), "segments")

cats = c.get("/api/categories", headers=h).json()
cat = next(x for x in cats if x["name"] == "家屬額外要求")
case_q = c.post("/api/cases", headers=h, json={
    "category_id": cat["id"], "template_id": cat["templates"][0]["id"],
    "text": "家屬王小姐要求每晚多餵一次點心，住民有糖尿病紀錄，想確認能不能配合。",
    "client_request_id": str(uuid.uuid4())}).json()
print("quick case", case_q["number"], case_q.get("assignee"))

sup = c.post("/api/auth/login", json={"username": "sup_happy_a", "password": accounts["sup_happy_a"]}).json()
sh = {"Authorization": f"Bearer {sup['session_token']}"}
case2 = qa2["case"]["id"]
c.post(f"/api/admin/cases/{case2}/take", headers=sh)
rep = c.post(f"/api/admin/cases/{case2}/reply", headers=sh, json={
    "text": "依本機構《異常事件處理作業程序》於 48 小時內完成異常事件紀錄，並於交班時告知護理站。營運規範第 3 條與機構 SOP 的時限不一致，已提報主任修訂內規版本。",
    "client_request_id": str(uuid.uuid4())}).json()
print("reply", rep["reply_saved"], rep["notification"]["status"])
time.sleep(4)
admin = c.post("/api/auth/login", json={"username": "admin_happy", "password": accounts["admin_happy"]}).json()

out.write_text(json.dumps({
    "caregiver_token": tok, "supervisor_token": sup["session_token"], "admin_token": admin["session_token"],
    "qa_answered": qa1["id"], "qa_conflict": qa2["id"], "qa_clinical": qa3["id"],
    "case_conflict": case2, "case_quick": case_q["id"], "transcript": tid, "category": cat["id"],
}, ensure_ascii=False, indent=1), encoding="utf-8")
print("written", out)

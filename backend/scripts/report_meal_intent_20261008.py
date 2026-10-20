import json,hashlib,xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
ROOT=Path(__file__).resolve().parents[2]
r=json.loads((ROOT/'docs/meal_intent_20261008_replay.json').read_text(encoding='utf-8'))
a=json.loads((ROOT/'docs/meal_intent_20261008_before_analysis.json').read_text(encoding='utf-8'))
b=sorted((ROOT/'backups').glob('meal_intent_*'))[-1]
before=json.loads((b/'core_before.json').read_text(encoding='utf-8'))
after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'backend/app/services').glob('*.py')}
assert before['qa_policy.py']==after['qa_policy.py']
assert sorted(k for k in before if before[k]!=after[k])==['qa_graph.py','query_understanding.py','retrieval_gate.py']
(b/'core_after.json').write_text(json.dumps(after,indent=2),encoding='utf-8')
t=ET.parse(ROOT/'docs/meal_intent_20261008_tests.xml').getroot()[0].attrib
assert t['failures']==t['errors']=='0'
lines=['# 進食規範與紀錄意圖：局部修正（2026-10-08）','',f'建立時間：{datetime.now().isoformat()}；備份：`{b}`。','',
'## 最新 QA 根因','',
'原喘息題不是沒有召回：正確疑義文件 rank1，coverage=0.3041、vector=0.3656、body_topic=title_topic=0.75，卻是 permission_rule_missing。clinical 沒攔截（risk_codes=[]）。正文「居家式喘息服務所含之進食可包含」沒有被原 normative／scope regex 辨識；居家喘息与居家式喘息也未作詞組對應。','',
'原紀錄題 risk_codes=[]，已由 evidence_selection 辨識 requested_field=record_items，但查詢意圖沒有約束正文紀錄需求，主題仍是進食；field_support 只針對家訪／電訪列點。因此進食案例通過 gate，沒有 fact_chunk_ids，送入 LLM 後回答輔具與進食技巧。主因是意圖／topic 及 gate 證據類型錯置；選證沿用 admitted 動作資料，進一步放大錯置，並非只改 prompt 能解決。','',
'下列 top10 取原 gate.candidates 排序，前8分數取原 checks；9/10 combined 未保存，不重算冒充原 QA。正文與 locator 以 SQL READ ONLY 補足。原始 QA：meal_intent_20261008_original.json；還原：meal_intent_20261008_before_analysis.json。','']
for q in a:
 lines += [f'### {q["question"]}','',f'QA id={q["qa_id"]}；created_at={q["created_at"]}。','',q['answer'],'','|rank|document／locator|chunk ID|combined|gate reason|','|---:|---|---|---:|---|']
 for x in q['top10']:
  score=x['scores'] or {}; lines.append(f'|{x["rank"]}|{x["title"]}／{x["locator"].replace("|","／")}|{x["id"]}|{score.get("combined","未保存")}|{x["gate"]["reason"]}|')
 lines += ['',f'Gate passed count={len(q["gate_passed"])}；selected evidence：','']
 for e in q['selected']:lines += [f'- `{e["id"]}`：{e["title"]}／{e["locator"]}']
lines += ['','## 最小變更','',
'- query_understanding.py：共用 record_intent 處理要記什麼／怎麼記（錄）／要不要記錄／留紀錄／紀錄什麼；紀錄題的進食動作作為服務背景，召回服務紀錄／紀錄內容，保留原問題供 risk 與 LLM。添加餵飯動作同義詞、居家喘息↔居家式喘息情境同義詞，未寫文件 ID／完整問題特判。','',
'- retrieval_gate.py：補可包含／不宜的規範述語及服務所含／包含的範圍語法，仍要求同一有界正文視窗中主題＋規範＋範圍共同命中；紀錄意圖另要求正文有紀錄依據（record_evidence_missing），排除只有操作技巧的 chunk。所有數值 gate 門檻原封不動，不靠 title 或 combined 單獨放行。','',
'- qa_graph.py：紀錄意圖與權限／回報一樣，只選 gate-admitted 證據，防止 focus／adjacency 再帶入無紀錄依據的技巧段；checks.query_intent 可稽核。top_k 未增加，prompt 未改。','',
'原 clarify 曾因把紀錄視為具體動作而測試退化，已修正：情境同義詞與動作詞分開，不修改 clarification_reason，原「這個紀錄可以這樣弄嗎？」仍 unspecified_action。','',
'qa_policy.py／吞嚥風險完全未變；risk SHA256：`'+after['qa_policy.py']+'`。retrieval.py、evidence_selection.py、role consistency、verification、KB 未修改。policy version 仍 swallowing-risk.1，這次 delta 以備份與 source hash 區分，不覆寫先前 freeze。','',
'## 最終驗證','',f'py_compile 成功。完整 suite：{t["tests"]}/{t["tests"]} passed，failures={t["failures"]}、errors={t["errors"]}、skipped={t["skipped"]}，{t["time"]}秒。新增 test_meal_intent.py 共11 tests。僅既有 anyio deprecation warning。','',
'實際 graph 使用 HAPPY 的 current KB、真實 provider，SQL READ ONLY，不建立 QA／轉交案件。全 A～F路由／證據檢查通過，以下不是單純 regex 結果。','',
'|ID|question|outcome|reason|query intent|latency ms|','|---|---|---|---|---|---:|']
for x in r['runs']:lines.append(f'|{x["id"]}|{x["question"]}|{x["outcome"]}|{x["reason"]}|{x["checks"].get("query_intent","risk before retrieval")}|{x["latency_ms"]}|')
for x in r['runs']:
 lines += ['',f'### {x["id"]} 實際 top10／gate／selected evidence／answer','', '|rank|document／locator|combined|coverage|vector|gate|','|---:|---|---:|---:|---:|---|']
 gate={g['chunk_id']:g for g in (x['checks'].get('retrieval_gate') or {}).get('candidates',[])}
 for item in x['top10']:
  g=gate.get(item['chunk_id'],{});lines.append(f'|{item["rank"]}|{item["title"]}／{item["locator"].replace("|","／")}|{item["combined"]}|{item["coverage"]}|{item["vector"]}|{g.get("reason")}|')
 if not x['top10']:lines += ['','未執行 retrieval／LLM。']
 lines += ['','Selected：']
 for e in x['selected_evidence']:lines += [f'- {e["ref"]} `{e["chunk_id"]}`：{e["title"]}／{e["locator"]}']
 lines += ['','Answer：']+[c['text'] for c in (x['claims'] or [])]
lines += ['','## 結果界線','',
'B/C 使用真正含「進食可包含協助餵食」的疑義正文，第1段為主要證據。D/E 使用《長照專業服務操作指引-附錄一服務紀錄參考格式》，回答服務次數／起訖時間與訓練紀錄內容，不再給進食技巧；該格式屬專業服務參考，不能把本輪 PASS 當作每個機構一般照顧服務必填欄位的完整核定。F 未分類成 record，現有召回引用喘息進食規範；使用者未指定喘息情境，適用條件仍需按原 KB／驗證判斷，本輪只驗證不誤當紀錄題，不宣稱進食操作答案已全面評估。','',
'A仍risk_clinical，無檢索、無具體臨床 claims；完整 suite 含上一輪吞嚥風險與既有安全測試。未重跑原40題完整自然語言 regression，未宣稱重新得到全 regression 指標。實際 scope KB hash與基準一致：`'+r['kb_hash_before']+'`。','',
'原始 UI 記錄不覆寫。新 Python graph 已验证，尚未重啟 UI backend；現行 UI 必須重新載入修改檔案後再測。所有數值門檻／risk／clarify 规则／KB 保持。實際 replay JSON：meal_intent_20261008_replay.json；JUnit：meal_intent_20261008_tests.xml。']
(ROOT/'docs/meal_intent_fix_20261008.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Report created; risk/core hash checks passed')

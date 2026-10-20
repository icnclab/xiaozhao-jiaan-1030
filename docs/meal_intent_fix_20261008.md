# 進食規範與紀錄意圖：局部修正（2026-10-08）

建立時間：2026-10-08T11:57:38.359666；備份：`C:\aa\ltc_care_installer_20260912\ltc_care\backups\meal_intent_20261008_115042`。

## 最新 QA 根因

原喘息題不是沒有召回：正確疑義文件 rank1，coverage=0.3041、vector=0.3656、body_topic=title_topic=0.75，卻是 permission_rule_missing。clinical 沒攔截（risk_codes=[]）。正文「居家式喘息服務所含之進食可包含」沒有被原 normative／scope regex 辨識；居家喘息与居家式喘息也未作詞組對應。

原紀錄題 risk_codes=[]，已由 evidence_selection 辨識 requested_field=record_items，但查詢意圖沒有約束正文紀錄需求，主題仍是進食；field_support 只針對家訪／電訪列點。因此進食案例通過 gate，沒有 fact_chunk_ids，送入 LLM 後回答輔具與進食技巧。主因是意圖／topic 及 gate 證據類型錯置；選證沿用 admitted 動作資料，進一步放大錯置，並非只改 prompt 能解決。

下列 top10 取原 gate.candidates 排序，前8分數取原 checks；9/10 combined 未保存，不重算冒充原 QA。正文與 locator 以 SQL READ ONLY 補足。原始 QA：meal_intent_20261008_original.json；還原：meal_intent_20261008_before_analysis.json。

### 今天協助長輩吃飯，要記什麼？

QA id=7dd20e65-cef5-4b55-8a22-2ec13b33fb7a；created_at=2026-10-08 03:48:10.612512+00:00。

在服務過程中，居服員應至少讓個案執行一次獨立進食與穿脫衣褲的活動（出處 1）。在進食方面，個案使用粗柄湯匙後較易抓握操作且不易掉落，左手輔助筷使用也較為便利，且餐椅高度可利用坐墊墊高以增加便利性（出處 1）。

|rank|document／locator|chunk ID|combined|gate reason|
|---:|---|---|---:|---|
|1|長照專業服務操作指引-附錄三-案例說明_公告／（二） 指導內容｜第 130 段|172264d7-c8d6-4d23-a1b0-810f9e8da778|0.4202|normalized_body_lexical_signal|
|2|長照專業服務操作指引-附錄三-案例說明_公告／(二)指導內容｜第 99 段|3394efd9-6eb4-4bf3-ade6-ff5a0130cd27|0.3509|normalized_body_lexical_signal|
|3|長照專業服務操作指引-附錄三-案例說明_公告／（二） 指導內容｜第 133 段|ca71b365-ed42-44e2-8452-f4b3afacb95e|0.3226|body_relevant_and_base_signal|
|4|長照專業服務操作指引-操作篇-共通操作指引_公告／（二） 如何引發個案的動機、說出需要專業服務的問題｜第 15 段|92d78ba2-da98-4df9-91fe-24d37bbcc165|0.2994|base_signal_insufficient|
|5|長照專業服務手冊／一、 安全進食：照顧者或個案能習得安全及有效率的進食模式及策｜第 27 段|fb5c6933-7b5f-402a-b5ad-4cb7874c3731|0.2889|body_topic_missing|
|6|長照專業服務手冊／一、 安全進食：照顧者或個案能習得安全及有效率的進食模式及策｜第 93 段|798097fb-103f-420f-8bdb-bd56ce4fe05b|0.2889|body_topic_missing|
|7|長照專業服務手冊／（一）安全進食：照顧者或個案能習得安全及有效率的進食模式及策｜第 43 段|cb7a38ba-735f-4dbc-a26a-82ea762cb050|0.288|body_topic_missing|
|8|長照專業服務手冊／（一）安全進食：照顧者或個案能習得安全及有效率的進食模式及策｜第 109 段|eec13fdd-2ac1-4268-bb3e-f1d954fe9e49|0.288|body_topic_missing|
|9|長照專業服務操作指引-附錄三-案例說明_公告／（二） 指導內容｜第 52 段|0efd3446-c72a-4fa1-9ffc-d7cef07a4677|未保存|body_relevant_and_base_signal|
|10|長照專業服務操作指引-附錄三-案例說明_公告／一、接案與轉介專業服務之流程｜第 72 段|b86d4c20-f226-4512-a672-d0da921b8f39|未保存|body_topic_missing|

Gate passed count=4；selected evidence：

- `172264d7-c8d6-4d23-a1b0-810f9e8da778`：長照專業服務操作指引-附錄三-案例說明_公告／（二） 指導內容｜第 130 段
- `3394efd9-6eb4-4bf3-ade6-ff5a0130cd27`：長照專業服務操作指引-附錄三-案例說明_公告／(二)指導內容｜第 99 段
- `ca71b365-ed42-44e2-8452-f4b3afacb95e`：長照專業服務操作指引-附錄三-案例說明_公告／（二） 指導內容｜第 133 段
- `0efd3446-c72a-4fa1-9ffc-d7cef07a4677`：長照專業服務操作指引-附錄三-案例說明_公告／（二） 指導內容｜第 52 段
### 居家喘息可以協助進食嗎？

QA id=c5c8e1be-58c5-4697-81b9-aee45a5964d2；created_at=2026-10-08 03:48:01.907379+00:00。

這個問題系統無法直接回答（知識庫中找不到足夠依據）。

|rank|document／locator|chunk ID|combined|gate reason|
|---:|---|---|---:|---|
|1|居家式喘息服務進食服務疑義-衛部顧字第1091962544號／第 1 段|21f1068a-f790-4dc5-91aa-ad32d2c5a5d4|0.8763|permission_rule_missing|
|2|居家式喘息服務進食服務疑義-衛部顧字第1091962544號／第 2 段|30687c35-3e5c-4169-bcf7-fccf818a3bb5|0.7736|permission_rule_missing|
|3|居家喘息服務實務使用疑義-口腔抽吸-衛部顧字第1091961599號／一、復貴局109年6月17日北市衛長字第1093007372｜第 2 段|1a675616-7e7d-432c-8228-a86f2fce4b46|0.7537|permission_rule_missing|
|4|居家喘息服務實務使用疑義-口腔抽吸-衛部顧字第1091961599號／第 1 段|dbc0a1c0-c71d-4944-9536-ad9fae701aa1|0.6008|body_topic_missing|
|5|附表四 照顧組合表／二、本組合以二小時為一給（支）付單位，｜第 243 段|385b5b8c-f64e-470e-85ee-3687b41c4449|0.5034|permission_rule_missing|
|6|長照專業服務操作指引-附錄三-案例說明_公告／（二） 核定給付額度項目(僅列舉部分項目)｜第 13 段|34f6ad70-5a55-4a15-81f8-e16caafabf1a|0.467|permission_rule_missing|
|7|附表四 照顧組合表／二、本組合以小時為給（支）付單位。｜第 241 段|6cded74d-776e-43cd-bdce-f33c27aedc3f|0.4564|permission_rule_missing|
|8|長照專業服務操作指引-附錄三-案例說明_公告／（二） 核定給付額度項目(僅列舉部分項目)｜第 44 段|cfdccbb2-9139-476a-8b71-61a9529ee3f3|0.4325|permission_rule_missing|
|9|長照專業服務操作指引-附錄三-案例說明_公告／（二） 核定給付額度項目(僅列舉部分項目)｜第 123 段|6e10dbbc-9a39-4246-b043-6a1b5d12721e|未保存|permission_rule_missing|
|10|長照專業服務操作指引-附錄三-案例說明_公告／一、接案與轉介專業服務之流程｜第 3 段|4c49745f-ff07-4601-9233-f692feed6bc1|未保存|permission_rule_missing|

Gate passed count=0；selected evidence：


## 最小變更

- query_understanding.py：共用 record_intent 處理要記什麼／怎麼記（錄）／要不要記錄／留紀錄／紀錄什麼；紀錄題的進食動作作為服務背景，召回服務紀錄／紀錄內容，保留原問題供 risk 與 LLM。添加餵飯動作同義詞、居家喘息↔居家式喘息情境同義詞，未寫文件 ID／完整問題特判。

- retrieval_gate.py：補可包含／不宜的規範述語及服務所含／包含的範圍語法，仍要求同一有界正文視窗中主題＋規範＋範圍共同命中；紀錄意圖另要求正文有紀錄依據（record_evidence_missing），排除只有操作技巧的 chunk。所有數值 gate 門檻原封不動，不靠 title 或 combined 單獨放行。

- qa_graph.py：紀錄意圖與權限／回報一樣，只選 gate-admitted 證據，防止 focus／adjacency 再帶入無紀錄依據的技巧段；checks.query_intent 可稽核。top_k 未增加，prompt 未改。

原 clarify 曾因把紀錄視為具體動作而測試退化，已修正：情境同義詞與動作詞分開，不修改 clarification_reason，原「這個紀錄可以這樣弄嗎？」仍 unspecified_action。

qa_policy.py／吞嚥風險完全未變；risk SHA256：`6f4ffe29234a81705acb011521119d1c18ca729f11fe00d7ea35a5b924c55c0f`。retrieval.py、evidence_selection.py、role consistency、verification、KB 未修改。policy version 仍 swallowing-risk.1，這次 delta 以備份與 source hash 區分，不覆寫先前 freeze。

## 最終驗證

py_compile 成功。完整 suite：171/171 passed，failures=0、errors=0、skipped=0，63.789秒。新增 test_meal_intent.py 共11 tests。僅既有 anyio deprecation warning。

實際 graph 使用 HAPPY 的 current KB、真實 provider，SQL READ ONLY，不建立 QA／轉交案件。全 A～F路由／證據檢查通過，以下不是單純 regex 結果。

|ID|question|outcome|reason|query intent|latency ms|
|---|---|---|---|---|---:|
|A|長輩吃飯一直嗆到怎麼辦？|escalate|risk_clinical|risk before retrieval|14.802|
|B|居家喘息可以協助進食嗎？|answer|None|permission|2594.404|
|C|居家式喘息能幫忙餵飯嗎？|answer|None|permission|2251.933|
|D|今天協助長輩吃飯，要記什麼？|answer|None|record|2662.286|
|E|進食服務要不要留紀錄？|answer|None|record|2566.497|
|F|長輩吃飯要怎麼協助？|answer|None|general|2139.449|

### A 實際 top10／gate／selected evidence／answer

|rank|document／locator|combined|coverage|vector|gate|
|---:|---|---:|---:|---:|---|

未執行 retrieval／LLM。

Selected：

Answer：

### B 實際 top10／gate／selected evidence／answer

|rank|document／locator|combined|coverage|vector|gate|
|---:|---|---:|---:|---:|---|
|1|居家式喘息服務進食服務疑義-衛部顧字第1091962544號／第 1 段|1.2222|0.3041|0.3381|body_relevant_and_base_signal|
|2|居家式喘息服務進食服務疑義-衛部顧字第1091962544號／第 2 段|0.8045|0.2597|0.3388|permission_rule_missing|
|3|居家喘息服務實務使用疑義-口腔抽吸-衛部顧字第1091961599號／一、復貴局109年6月17日北市衛長字第1093007372｜第 2 段|0.5109|0.3041|0.081|permission_rule_missing|
|4|居家喘息服務實務使用疑義-口腔抽吸-衛部顧字第1091961599號／第 1 段|0.4466|0.33|0.1335|body_topic_missing|
|5|附表四 照顧組合表／二、本組合以二小時為一給（支）付單位，｜第 243 段|0.4166|0.33|0.1497|permission_rule_missing|
|6|附表四 照顧組合表／二、本組合以小時為給（支）付單位。｜第 241 段|0.3951|0.33|0.1935|permission_rule_missing|
|7|長照專業服務操作指引-附錄三-案例說明_公告／（二） 核定給付額度項目(僅列舉部分項目)｜第 13 段|0.39|0.33|0.1822|permission_rule_missing|
|8|附表四 照顧組合表／二、本組合係為配合長照給付對象生理狀況｜第 47 段|0.3615|0.308|0.2655|permission_rule_missing|
|9|長照專業服務操作指引-附錄三-案例說明_公告／（二） 核定給付額度項目(僅列舉部分項目)｜第 123 段|0.3497|0.33|0.0926|permission_rule_missing|
|10|長照專業服務操作指引-附錄三-案例說明_公告／（二） 核定給付額度項目(僅列舉部分項目)｜第 44 段|0.3472|0.33|0.087|permission_rule_missing|

Selected：
- E1 `21f1068a-f790-4dc5-91aa-ad32d2c5a5d4`：居家式喘息服務進食服務疑義-衛部顧字第1091962544號／第 1 段

Answer：
居家式喘息服務所含之「進食」可包含協助餵食（或灌食）等相關服務。
居家式喘息服務的「進食」可包含依居家現有食材備餐、加熱現有飯菜（或管灌飲食）、準備進食環境及餐具、協助餵食（或灌食）、善後工作及清潔等。
照服員在喘息服務期間不宜外出採買。

### C 實際 top10／gate／selected evidence／answer

|rank|document／locator|combined|coverage|vector|gate|
|---:|---|---:|---:|---:|---|
|1|居家式喘息服務進食服務疑義-衛部顧字第1091962544號／第 1 段|1.1483|0.3899|0.1741|body_relevant_and_base_signal|
|2|居家式喘息服務進食服務疑義-衛部顧字第1091962544號／第 2 段|0.7497|0.1035|0.2171|permission_rule_missing|
|3|居家喘息服務實務使用疑義-口腔抽吸-衛部顧字第1091961599號／一、復貴局109年6月17日北市衛長字第1093007372｜第 2 段|0.4911|0.1416|0.037|permission_rule_missing|
|4|附表四 照顧組合表／二、本組合以二小時為一給（支）付單位，｜第 243 段|0.3983|0.1416|0.1089|permission_rule_missing|
|5|附表四 照顧組合表／二、本組合以小時為給（支）付單位。｜第 241 段|0.3666|0.1416|0.1302|permission_rule_missing|
|6|長照專業服務操作指引-附錄三-案例說明_公告／（二） 核定給付額度項目(僅列舉部分項目)｜第 13 段|0.3662|0.1416|0.1293|permission_rule_missing|
|7|長照專業服務操作指引-附錄三-案例說明_公告／（二） 核定給付額度項目(僅列舉部分項目)｜第 123 段|0.3411|0.1416|0.0735|permission_rule_missing|
|8|長照專業服務操作指引-附錄三-案例說明_公告／一、接案與轉介專業服務之流程｜第 3 段|0.3293|0.1416|0.0472|permission_rule_missing|
|9|長照專業服務操作指引-附錄三-案例說明_公告／（二） 核定給付額度項目(僅列舉部分項目)｜第 44 段|0.329|0.1416|0.0466|permission_rule_missing|
|10|居家喘息服務實務使用疑義-口腔抽吸-衛部顧字第1091961599號／第 1 段|0.3025|0.1416|0.0436|body_topic_missing|

Selected：
- E1 `21f1068a-f790-4dc5-91aa-ad32d2c5a5d4`：居家式喘息服務進食服務疑義-衛部顧字第1091962544號／第 1 段

Answer：
居家式喘息服務所含之「進食」可包含協助餵食（或灌食）
居家式喘息服務的「進食」內容包含依居家現有食材備餐、加熱現有飯菜（或管灌飲食）、準備進食環境及餐具、協助餵食（或灌食）、善後工作及清潔。
照服員在喘息服務中不宜外出採買。

### D 實際 top10／gate／selected evidence／answer

|rank|document／locator|combined|coverage|vector|gate|
|---:|---|---:|---:|---:|---|
|1|長照專業服務操作指引-附錄一服務紀錄參考格式_公告／三、服務紀錄表（每次服務均需填寫）｜第 12 段|0.9379|0.0333|0.1953|normalized_body_lexical_signal|
|2|長照專業服務操作指引-附錄一服務紀錄參考格式_公告／二、評估表（含結案紀錄）暨服務計畫建議大綱內容｜第 10 段|0.9254|0.0333|0.1676|normalized_body_lexical_signal|
|3|長照專業服務操作指引-附錄一服務紀錄參考格式_公告／二、評估表（含結案紀錄）暨服務計畫建議大綱內容｜第 9 段|0.9089|0.0808|0.1308|normalized_body_lexical_signal|
|4|長照專業服務操作指引-附錄一服務紀錄參考格式_公告／第 1 段|0.8566|0.0333|0.0147|normalized_body_lexical_signal|
|5|附表四 照顧組合表／二、申請費用應檢附服務紀錄、照顧計畫異｜第 6 段|0.6943|0.0|0.3206|normalized_body_lexical_signal|
|6|居家服務督導員工作手冊／（一）	服務記錄檢閱與分析：｜第 388 段|0.6878|0.0|0.3063|normalized_body_lexical_signal|
|7|長照專業服務操作指引-操作篇-共通操作指引_公告／一、服務紀錄必要項目及參考格式｜第 48 段|0.6858|0.0333|0.3017|normalized_body_lexical_signal|
|8|長照專業服務手冊／（五）製作紀錄｜第 26 段|0.6637|0.0333|0.2527|normalized_body_lexical_signal|
|9|長照專業服務手冊／（五）製作紀錄｜第 92 段|0.6632|0.0333|0.2517|normalized_body_lexical_signal|
|10|居家服務督導員工作手冊／五、	記錄保存完整｜第 245 段|0.662|0.0|0.249|normalized_body_lexical_signal|

Selected：
- E1 `8fb037ae-7a32-43b9-9dc9-d685fe0af136`：長照專業服務操作指引-附錄一服務紀錄參考格式_公告／三、服務紀錄表（每次服務均需填寫）｜第 12 段
- E2 `d8aed2a7-e519-468e-89a5-dc4daea7e317`：長照專業服務操作指引-附錄一服務紀錄參考格式_公告／二、評估表（含結案紀錄）暨服務計畫建議大綱內容｜第 10 段
- E3 `cfacedf5-54b6-44bf-a8d4-73482bca49fe`：長照專業服務操作指引-附錄一服務紀錄參考格式_公告／二、評估表（含結案紀錄）暨服務計畫建議大綱內容｜第 9 段
- E4 `d0eba4f0-9e35-48ec-a858-8a6e1968e267`：長照專業服務操作指引-附錄一服務紀錄參考格式_公告／第 1 段
- E5 `99cce991-dd8a-4206-bdc2-4004c066a821`：附表四 照顧組合表／二、申請費用應檢附服務紀錄、照顧計畫異｜第 6 段

Answer：
您應在服務紀錄表上填寫服務次數和時間，並在訓練紀錄中補充描述案家執行目標活動的情況，與之前表現的比較，以及分析阻礙目標達成的原因等。
服務紀錄表需要填寫服務次數和服務起訖時間。
訓練紀錄應包含居家指導訓練內容，並建議補充描述案家執行目標活動的情況、與之前表現的比較，以及分析阻礙目標達成的原因等。

### E 實際 top10／gate／selected evidence／answer

|rank|document／locator|combined|coverage|vector|gate|
|---:|---|---:|---:|---:|---|
|1|長照專業服務操作指引-附錄一服務紀錄參考格式_公告／三、服務紀錄表（每次服務均需填寫）｜第 12 段|0.9607|0.064|0.246|normalized_body_lexical_signal|
|2|長照專業服務操作指引-附錄一服務紀錄參考格式_公告／第 2 段|0.9533|0.064|0.2296|normalized_body_lexical_signal|
|3|長照專業服務操作指引-附錄一服務紀錄參考格式_公告／第 1 段|0.858|0.064|0.0178|normalized_body_lexical_signal|
|4|居家服務督導員工作手冊／（一）	服務記錄檢閱與分析：｜第 388 段|0.7186|0.064|0.3746|normalized_body_lexical_signal|
|5|附表四 照顧組合表／二、申請費用應檢附服務紀錄、照顧計畫異｜第 6 段|0.7021|0.064|0.3379|normalized_body_lexical_signal|
|6|居家服務督導員工作手冊／（二） 常用工具｜第 362 段|0.6969|0.064|0.3265|normalized_body_lexical_signal|
|7|長照專業服務操作指引-操作篇-共通操作指引_公告／一、服務紀錄必要項目及參考格式｜第 48 段|0.6925|0.064|0.3167|normalized_body_lexical_signal|
|8|居家服務督導員工作手冊／三、 服務紀錄（含服務計畫、家電訪紀錄等）應依相關法規規定，｜第 379 段|0.6894|0.064|0.3098|normalized_body_lexical_signal|
|9|長照專業服務操作指引-附錄二-居家護理指導與諮詢服務的處置指引_公告／(二) 依照照顧服務管理資訊平台之要求上傳申報資料。｜第 187 段|0.6859|0.064|0.302|normalized_body_lexical_signal|
|10|居家服務督導員工作手冊／一、	事前審閱服務使用者排班、照顧計畫與服務記錄摘要，以掌握｜第 370 段|0.6852|0.064|0.3005|normalized_body_lexical_signal|

Selected：
- E1 `8fb037ae-7a32-43b9-9dc9-d685fe0af136`：長照專業服務操作指引-附錄一服務紀錄參考格式_公告／三、服務紀錄表（每次服務均需填寫）｜第 12 段
- E2 `9ff7f3d2-f8a9-4884-9e43-366214899c26`：長照專業服務操作指引-附錄一服務紀錄參考格式_公告／第 2 段
- E3 `d0eba4f0-9e35-48ec-a858-8a6e1968e267`：長照專業服務操作指引-附錄一服務紀錄參考格式_公告／第 1 段
- E4 `cfacedf5-54b6-44bf-a8d4-73482bca49fe`：長照專業服務操作指引-附錄一服務紀錄參考格式_公告／二、評估表（含結案紀錄）暨服務計畫建議大綱內容｜第 9 段
- E5 `d8aed2a7-e519-468e-89a5-dc4daea7e317`：長照專業服務操作指引-附錄一服務紀錄參考格式_公告／二、評估表（含結案紀錄）暨服務計畫建議大綱內容｜第 10 段

Answer：
服務紀錄表（每次服務均需填寫）中，有「訓練紀錄」的欄位，建議可補充描述案家執行目標活動的情況，與之前表現之比較，分析阻礙目標達成的原因等。
服務紀錄表是每次服務都必須填寫的。
紀錄內容應包含居家指導訓練內容。

### F 實際 top10／gate／selected evidence／answer

|rank|document／locator|combined|coverage|vector|gate|
|---:|---|---:|---:|---:|---|
|1|居家式喘息服務進食服務疑義-衛部顧字第1091962544號／第 2 段|0.9249|0.0919|0.1666|normalized_body_lexical_signal|
|2|居家式喘息服務進食服務疑義-衛部顧字第1091962544號／第 1 段|0.8934|0.0919|0.0965|normalized_body_lexical_signal|
|3|長照專業服務操作指引-附錄三-案例說明_公告／（二） 指導內容｜第 130 段|0.6497|0.3474|0.2215|body_relevant_and_base_signal|
|4|長照專業服務操作指引-附錄三-案例說明_公告／（二） 指導內容｜第 133 段|0.6429|0.4392|0.2065|body_relevant_and_base_signal|
|5|長照專業服務手冊／一、 安全進食：照顧者或個案能習得安全及有效率的進食模式及策｜第 27 段|0.6295|0.0646|0.1766|normalized_body_lexical_signal|
|6|長照專業服務手冊／一、 安全進食：照顧者或個案能習得安全及有效率的進食模式及策｜第 93 段|0.6295|0.0646|0.1766|normalized_body_lexical_signal|
|7|長照專業服務手冊／（一）安全進食：照顧者或個案能習得安全及有效率的進食模式及策｜第 43 段|0.6286|0.0646|0.1747|normalized_body_lexical_signal|
|8|長照專業服務手冊／（一）安全進食：照顧者或個案能習得安全及有效率的進食模式及策｜第 109 段|0.6286|0.0646|0.1747|normalized_body_lexical_signal|
|9|長照專業服務操作指引-附錄三-案例說明_公告／一、接案與轉介專業服務之流程｜第 71 段|0.6264|0.1565|0.1698|normalized_body_lexical_signal|
|10|長照專業服務操作指引-附錄三-案例說明_公告／（二） 指導內容｜第 53 段|0.6263|0.1565|0.1696|normalized_body_lexical_signal|

Selected：
- E1 `30687c35-3e5c-4169-bcf7-fccf818a3bb5`：居家式喘息服務進食服務疑義-衛部顧字第1091962544號／第 2 段
- E2 `21f1068a-f790-4dc5-91aa-ad32d2c5a5d4`：居家式喘息服務進食服務疑義-衛部顧字第1091962544號／第 1 段

Answer：
居家式喘息服務所含之「進食」可包含依居家現有食材備餐、加熱現有飯菜（或管灌飲食）、進食環境（含長照需要者安置）準備、餐具準備、協助餵食（或灌食）、進食環境及餐具準備、與備餐後用具及餐具善後工作及清潔。
照服員不宜於喘息服務外出採買。

## 結果界線

B/C 使用真正含「進食可包含協助餵食」的疑義正文，第1段為主要證據。D/E 使用《長照專業服務操作指引-附錄一服務紀錄參考格式》，回答服務次數／起訖時間與訓練紀錄內容，不再給進食技巧；該格式屬專業服務參考，不能把本輪 PASS 當作每個機構一般照顧服務必填欄位的完整核定。F 未分類成 record，現有召回引用喘息進食規範；使用者未指定喘息情境，適用條件仍需按原 KB／驗證判斷，本輪只驗證不誤當紀錄題，不宣稱進食操作答案已全面評估。

A仍risk_clinical，無檢索、無具體臨床 claims；完整 suite 含上一輪吞嚥風險與既有安全測試。未重跑原40題完整自然語言 regression，未宣稱重新得到全 regression 指標。實際 scope KB hash與基準一致：`d624bfd9675ee8edec96c1635336704d05059cfaaf68f0ec0d04ade4f07d5be7`。

原始 UI 記錄不覆寫。新 Python graph 已验证，尚未重啟 UI backend；現行 UI 必須重新載入修改檔案後再測。所有數值門檻／risk／clarify 规则／KB 保持。實際 replay JSON：meal_intent_20261008_replay.json；JUnit：meal_intent_20261008_tests.xml。

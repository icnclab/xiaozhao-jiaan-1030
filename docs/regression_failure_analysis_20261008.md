# Regression 失敗案例根因分析（2026-10-08）

本輪僅分析與寫入此 Markdown；沒有修改任何程式、法規、知識庫、原 regression JSON 或評分結果。未重新執行 retrieve／LLM，也未重跑 tests。

分析範圍：7 個 false refusal（各兩輪，共 14 次）、保存年限漏答 Q12（2 次）、citation role mismatch Q09（僅第二輪 1 次）。共 9 題、17 個失敗實例；Q09 第一輪列為對照。expected outcome 全部為 answer。

## 證據來源與記錄限制

主要來源：`docs/regression_20261008.json`，SHA256 `e879e6845a73d1f2228de0df7dc80087800e7d58265e8cbab49ad60931f54e1d`。回歸政策 `2026-10-08.colloquial.1`，HAPPY 虛構居家機構；不是嘉安正式場域資料。

逐題核查 top5、完整 gate candidates、selected evidence、LLM flags、claims 與 timings。已唯讀查閱回歸 snapshot 中的正式 KB 原文；2016 個 chunk 的全文 hash 與回歸 snapshot 相同。核心 8 個檔案 hash 亦與回歸測量前一致。主題 groups 以這些未變的既有函式重新計算，只做語詞分析，沒有重新檢索或生成。

完整原始 LLM CandidateAnswer / provider raw response 沒有存入 regression JSON。可列出的 candidate 訊號只有 checks.llm_flags（needs_human、conflict、reason）；claims 是驗證後保存的主張，不能冒稱為完整原始 candidate。未呼叫 LLM 的題目明列「未執行」；已呼叫但未存原文的題目明列「未完整保存」，不補造。

Gate candidates 的順序由原 qa_graph 記錄 retrieved results 順序；下文的完整候選位置據此計算。Top5 只是效能指標，不能代表完整候選都沒有正確答案。兩輪 top5、selected evidence 在這 9 題均完全相同；因此 top5 表共用，但 candidate flags、verify、答案與 latency 逐輪列出。

Failure class 僅使用 knowledge gap、retrieval failure、gate failure、clarify classification、risk classification、LLM generation、verification、citation mapping。主因是最直接阻斷／破壞答案的層級；次因可並列。相鄰補段／focus／選證失敗併入 retrieval failure，另於文字明示位置。

## 結論與分類摘要

這 9 題的 KB 均有現行正確依據；沒有證據支持把它們歸 knowledge gap。七個 false refusal 的 risk_codes 全空，且沒有先走 clarify，故沒有 risk classification 或 clarify classification 失敗。Q09 的 E1 指向正確段落，未發現 citation mapping 錯誤；角色錯置屬生成與驗證問題。

|ID|question|主 failure class|次 failure class|KB 實有依據|局部修正評估|
|---|---|---|---|---|---|
|Q01|照顧服務員是否可執行一般傷口更換敷料？|gate failure|—|是|有局部切入點；尚未修／驗證|
|Q03|照顧服務員是否可執行傷口簡易清潔？|gate failure|—|是|有局部切入點；尚未修／驗證|
|Q05|居家服務過程中發生跌倒事件，應如何通報主管？|gate failure|retrieval failure|是|有局部切入點；尚未修／驗證|
|Q07|居家服務使用者跌倒，是否需要回報督導？|gate failure|retrieval failure|是|有局部切入點；尚未修／驗證|
|Q13|居家服務督導員的家訪記錄應評估哪些重點？|retrieval failure|—|是|有局部切入點；尚未修／驗證|
|Q14|家訪要記哪些重點？|gate failure|—|是|有局部切入點；尚未修／驗證|
|Q16|電訪要記什麼？|retrieval failure|gate failure|是|有局部切入點；尚未修／驗證|
|Q12|服務紀錄要留幾年？|retrieval failure|LLM generation、verification|是|有局部切入點；尚未修／驗證|
|Q09|家屬要求照服員執行服務契約工作範圍外的事項，應如何處理？|LLM generation|verification|是|有局部切入點；尚未修／驗證|

兩個需要更正的根因解讀：Q07 雖 top5 未命中，正確段落已在完整候選中且皆被 gate 擋下，主因應含 gate；Q13 則正確段落通過 gate，卻被同文件相鄰選證策略排除，LLM insufficient 是合理保守結果，不能單憑 final reason 把它認定成生成失敗。

下列「局部修正」僅為範圍判斷，並未提出已驗證修法，也不保證只改一處即可解決。共享語詞或選證規則都可能影響其他 PASS 題。

## Q01 照顧服務員是否可執行一般傷口更換敷料？

- Question：照顧服務員是否可執行一般傷口更換敷料？
- Expected outcome：answer
- Actual outcome：R1=no_evidence（graph=escalate）；R2=no_evidence（graph=escalate）
- Failure class：主 `gate failure`
- KB 實際有正確依據：是；在回歸版本範圍及 hash 一致的正文中核實。

### Retrieval top5（兩輪相同）

|rank|document / locator|chunk ID|combined|coverage|vector|gate result / reason|
|---|---|---|---|---|---|---|
|1|照顧服務員執行傷口換藥疑義-(1090119919) / 四、本案貴府詢及服務對象需在宅進行一般傷口更換敷料、傷口｜第 4 段|03692e5f-caeb-434d-b2c0-ad5cea7dd150|0.6053|0.6215|0.2432|False / permission_rule_missing|
|2|長照專業服務操作指引-附錄二-居家護理指導與諮詢服務的處置指引_公告 / (一) 傷口處理原則｜第 67 段|fb290eb0-ad77-4d93-9953-42074dfcf50b|0.4230|0.1666|0.2483|False / permission_rule_missing|
|3|長照專業服務操作指引-附錄二-居家護理指導與諮詢服務的處置指引_公告 / (二) 基本傷口換藥技術｜第 79 段|78d371bf-6659-48f7-a172-6de3b1c21dc2|0.4134|0.1004|0.3386|False / permission_rule_missing|
|4|長照專業服務操作指引-附錄二-居家護理指導與諮詢服務的處置指引_公告 / (二) 基本傷口換藥技術｜第 78 段|852b4557-e9f3-4455-918a-0dbdff0c7196|0.4010|0.1962|0.3111|False / permission_rule_missing|
|5|長照專業服務操作指引-附錄二-居家護理指導與諮詢服務的處置指引_公告 / (三) 全人照護模式之傷口評估｜第 53 段|8c6674c0-0acd-44f8-a6ec-8abb47e9b05a|0.3741|0.1994|0.2724|False / permission_rule_missing|

Top1 document/chunk：**照顧服務員執行傷口換藥疑義-(1090119919)**；四、本案貴府詢及服務對象需在宅進行一般傷口更換敷料、傷口｜第 4 段；`03692e5f-caeb-434d-b2c0-ad5cea7dd150`。

### 正確 KB 依據與完整候選位置

|rank（全候選）|正確 document / locator / chunk|admitted|reason|body_topic|rule_topic|procedure_topic|hybrid|normalized_hybrid|
|---|---|---|---|---|---|---|---|---|
|1|照顧服務員執行傷口換藥疑義-(1090119919) / 四、本案貴府詢及服務對象需在宅進行一般傷口更換敷料、傷口｜第 4 段 / `03692e5f-caeb-434d-b2c0-ad5cea7dd150`|False|permission_rule_missing|0.6667|0.6667|0.0000|0.4513|0.4953|

KB 正文摘錄（非新補內容）：

**照顧服務員執行傷口換藥疑義-(1090119919) / 四、本案貴府詢及服務對象需在宅進行一般傷口更換敷料、傷口｜第 4 段**

> 四、本案貴府詢及服務對象需在宅進行一般傷口更換敷料、傷口
> 簡易清潔等情，難謂無涉醫療專業判斷及醫療輔助行為，類
> 此個案，貴府允應審視個案事實及需求情形，連結居家醫療
> 或居家護理資源，提供長照需要者及其家庭必要協助。
> 正本：新北市政府衛生局
> 副本：本部長期照顧司
> 第2頁　共2頁

主題 groups（凍結版本重算）：

```json
[[["換藥"], ["換敷", "敷料", "更換"]], [["一般"]], [["傷口"]], [["否可"]], [["是否"]], [["般傷"]]]
```

### Gate result / selected evidence

R1：完整候選 76 個，admitted 0 個；focus=`null`。
R2：完整候選 76 個，admitted 0 個；focus=`null`。

Selected evidence：無；gate 沒有 admitted chunk，未進 LLM。

### LLM candidate / verification / final result

**Round 1**

LLM candidate：未執行生成；無候選。Verification：未執行。

Final reason：`no_evidence`；reason_detail：無。
Final answer：無（拒答／转人工）。
回歸 citation review：`{"passed": null, "refs_support_pass": false, "expected_chunk_selected": false, "fact_anchors_pass": false, "status": "Production refs/support + agent source review; not expert sign-off", "agent_source_review_pass": null, "review_note": "Not applicable; no final answer."}`。

**Round 2**

LLM candidate：未執行生成；無候選。Verification：未執行。

Final reason：`no_evidence`；reason_detail：無。
Final answer：無（拒答／转人工）。
回歸 citation review：`{"passed": null, "refs_support_pass": false, "expected_chunk_selected": false, "fact_anchors_pass": false, "status": "Production refs/support + agent source review; not expert sign-off", "agent_source_review_pass": null, "review_note": "Not applicable; no final answer."}`。

### Latency

|Round|total ms|retrieval node ms|LLM node ms|verification node ms|
|---|---|---|---|---|
|1|193.527|148.820|未執行|未執行|
|2|244.936|240.940|未執行|未執行|

### 根因、局部範圍與 PASS 題影響

正確第 4 段已排名第 1。主題 groups 共 6 組，殘留「是否」「否可」兩組問法字眼；正文／權限句僅命中 4/6，rule_topic=0.6667 未達 0.80。hybrid=0.4513、normalized_hybrid=0.4953 本已足夠；不是向量不足，也不是缺少業務依據。permission_intent 正確辨識，但 _FRAME 未完整清除「是否可」問法，導致語氣字眼變成需要正文支持的主題。

是否只需要局部修正：可先從共用主題抽取對正式可否語氣的處理局部分析；無需因此重寫 retrieval 架構。是否足夠仍須後續實作與回歸證明，本輪未修。

是否可能影響其他已通過題：是。可能影響 Q02 換藥、Q04 清傷口、其他資格／業務範圍題及原本應拒絕的操作技術題；不得把限制條件一併刪除。


## Q03 照顧服務員是否可執行傷口簡易清潔？

- Question：照顧服務員是否可執行傷口簡易清潔？
- Expected outcome：answer
- Actual outcome：R1=no_evidence（graph=escalate）；R2=no_evidence（graph=escalate）
- Failure class：主 `gate failure`
- KB 實際有正確依據：是；在回歸版本範圍及 hash 一致的正文中核實。

### Retrieval top5（兩輪相同）

|rank|document / locator|chunk ID|combined|coverage|vector|gate result / reason|
|---|---|---|---|---|---|---|
|1|照顧服務員執行傷口換藥疑義-(1090119919) / 四、本案貴府詢及服務對象需在宅進行一般傷口更換敷料、傷口｜第 4 段|03692e5f-caeb-434d-b2c0-ad5cea7dd150|0.8017|0.3392|0.1980|False / body_topic_missing|
|2|照顧服務員執行傷口換藥疑義-(1090119919) / 三、查本部於107年起推動長期照顧給付及支付基準，係提供直｜第 3 段|93312d9b-e3b6-40e0-a5d3-06f7cc938256|0.6545|0.2383|0.1298|False / body_topic_missing|
|3|照顧服務員執行傷口換藥疑義-(1090119919) / 二、有關照顧服務員可執行業務內容，參照本部101年6月28日｜第 2 段|bdd0b437-437b-4db4-8f9e-42b346786ae8|0.6077|0.2148|0.0545|False / body_topic_missing|
|4|照顧服務員執行傷口換藥疑義-(1090119919) / 第 1 段|87667fec-03ae-4bf7-b5fd-d3d28bfcaf8d|0.5352|0.1049|0.0277|False / body_topic_missing|
|5|長照專業服務操作指引-附錄二-居家護理指導與諮詢服務的處置指引_公告 / (一) 傷口處理原則｜第 67 段|fb290eb0-ad77-4d93-9953-42074dfcf50b|0.4967|0.1953|0.3479|False / permission_rule_missing|

Top1 document/chunk：**照顧服務員執行傷口換藥疑義-(1090119919)**；四、本案貴府詢及服務對象需在宅進行一般傷口更換敷料、傷口｜第 4 段；`03692e5f-caeb-434d-b2c0-ad5cea7dd150`。

### 正確 KB 依據與完整候選位置

|rank（全候選）|正確 document / locator / chunk|admitted|reason|body_topic|rule_topic|procedure_topic|hybrid|normalized_hybrid|
|---|---|---|---|---|---|---|---|---|
|1|照顧服務員執行傷口換藥疑義-(1090119919) / 四、本案貴府詢及服務對象需在宅進行一般傷口更換敷料、傷口｜第 4 段 / `03692e5f-caeb-434d-b2c0-ad5cea7dd150`|False|body_topic_missing|0.3333|0.3333|0.0000|0.2757|0.3367|

KB 正文摘錄（非新補內容）：

**照顧服務員執行傷口換藥疑義-(1090119919) / 四、本案貴府詢及服務對象需在宅進行一般傷口更換敷料、傷口｜第 4 段**

> 四、本案貴府詢及服務對象需在宅進行一般傷口更換敷料、傷口
> 簡易清潔等情，難謂無涉醫療專業判斷及醫療輔助行為，類
> 此個案，貴府允應審視個案事實及需求情形，連結居家醫療
> 或居家護理資源，提供長照需要者及其家庭必要協助。
> 正本：新北市政府衛生局
> 副本：本部長期照顧司
> 第2頁　共2頁

主題 groups（凍結版本重算）：

```json
[[["傷口", "清傷"], ["傷口", "清潔", "潔傷"], ["傷口", "洗傷", "清洗"], ["傷口", "口清", "清潔"], ["傷口", "口簡", "易清", "清潔", "簡易"]], [["否可"]], [["是否"]]]
```

### Gate result / selected evidence

R1：完整候選 83 個，admitted 0 個；focus=`null`。
R2：完整候選 83 個，admitted 0 個；focus=`null`。

Selected evidence：無；gate 沒有 admitted chunk，未進 LLM。

### LLM candidate / verification / final result

**Round 1**

LLM candidate：未執行生成；無候選。Verification：未執行。

Final reason：`no_evidence`；reason_detail：無。
Final answer：無（拒答／转人工）。
回歸 citation review：`{"passed": null, "refs_support_pass": false, "expected_chunk_selected": false, "fact_anchors_pass": false, "status": "Production refs/support + agent source review; not expert sign-off", "agent_source_review_pass": null, "review_note": "Not applicable; no final answer."}`。

**Round 2**

LLM candidate：未執行生成；無候選。Verification：未執行。

Final reason：`no_evidence`；reason_detail：無。
Final answer：無（拒答／转人工）。
回歸 citation review：`{"passed": null, "refs_support_pass": false, "expected_chunk_selected": false, "fact_anchors_pass": false, "status": "Production refs/support + agent source review; not expert sign-off", "agent_source_review_pass": null, "review_note": "Not applicable; no final answer."}`。

### Latency

|Round|total ms|retrieval node ms|LLM node ms|verification node ms|
|---|---|---|---|---|
|1|216.962|213.575|未執行|未執行|
|2|208.683|204.123|未執行|未執行|

### 根因、局部範圍與 PASS 題影響

正確第 4 段已排名第 1，title_topic=1.0，並確實有完整「傷口簡易清潔」。三組 topic 中卻有兩組「是否」「否可」；只命中清潔行為一組，body_topic=rule_topic=0.3333，首先被 body_topic_missing 擋下。這不是「傷口簡易清潔」同義詞不存在，與 Q01 同為正式問法殘餘字造成分母污染。

是否只需要局部修正：與 Q01 可共用局部主題語氣處理候選；不是降低正文門檻或讓標題單獨放行。

是否可能影響其他已通過題：是。可能影響 Q04 清傷口以及其他同義動作、permission gate。須保留臨床風險題與純操作技術不可回答權限的邊界。


## Q05 居家服務過程中發生跌倒事件，應如何通報主管？

- Question：居家服務過程中發生跌倒事件，應如何通報主管？
- Expected outcome：answer
- Actual outcome：R1=no_evidence（graph=escalate）；R2=no_evidence（graph=escalate）
- Failure class：主 `gate failure`；次 `retrieval failure`
- KB 實際有正確依據：是；在回歸版本範圍及 hash 一致的正文中核實。

### Retrieval top5（兩輪相同）

|rank|document / locator|chunk ID|combined|coverage|vector|gate result / reason|
|---|---|---|---|---|---|---|
|1|居家服務督導員工作手冊 / （一） 服務過程中｜第 423 段|d312889c-d03e-4bfc-9f85-ef260297274a|0.4793|0.4529|0.3531|False / reporting_rule_missing|
|2|居家服務督導員工作手冊 / 二、	依照各縣市主管機關亦公告相關通報辦法辦理：｜第 422 段|e1c13e52-491f-408b-a3c2-3fa206cc2177|0.4350|0.4056|0.3737|False / reporting_rule_missing|
|3|居家服務督導員工作手冊 / 第二節 常見意外事件處理及通報｜第 413 段|3f56e7c5-fe6a-45b4-80c1-6000e43fe726|0.4309|0.4234|0.2878|False / injection|
|4|居家服務督導員工作手冊 / （一） 跌倒｜第 433 段|ebf71bfe-9a60-40a7-8103-065b768ec928|0.3650|0.3043|0.2187|False / reporting_rule_missing|
|5|居家服務督導員工作手冊 / （一） 上述案例涉及之倫理兩難面向如下：｜第 535 段|aac4b76d-7786-4874-849e-80dd2c9319f8|0.3542|0.3315|0.2499|False / reporting_rule_missing|

Top1 document/chunk：**居家服務督導員工作手冊**；（一） 服務過程中｜第 423 段；`d312889c-d03e-4bfc-9f85-ef260297274a`。

### 正確 KB 依據與完整候選位置

|rank（全候選）|正確 document / locator / chunk|admitted|reason|body_topic|rule_topic|procedure_topic|hybrid|normalized_hybrid|
|---|---|---|---|---|---|---|---|---|
|1|居家服務督導員工作手冊 / （一） 服務過程中｜第 423 段 / `d312889c-d03e-4bfc-9f85-ef260297274a`|False|reporting_rule_missing|0.6000|0.0000|0.6000|0.4080|0.4793|
|14|居家服務督導員工作手冊 / （一） 跌倒｜第 434 段 / `5488a49f-5b3b-4fc3-88bc-301e2380918a`|False|reporting_rule_missing|0.3333|0.0000|0.2000|0.2458|0.2735|
|57|居家服務督導員工作手冊 / （二） 意外事件：｜第 399 段 / `c7e161eb-953b-40e5-975b-a25b3bc14fce`|False|body_topic_missing|0.2667|0.0000|0.2667|0.1201|0.1918|

KB 正文摘錄（非新補內容）：

**居家服務督導員工作手冊 / （一） 跌倒｜第 434 段**

> （一） 跌倒
> 1小時內向業務主管機關說明，
> 並同步至照管平台異動通報
> 4小時內向業務主管機關說明，
> 並同步至照管平台異動通報
> 服務使用者送醫，居督員進行後續追蹤。居督員視情況需求，協助調整後續班別，完整記
> 錄事發經過，並於24小時內完成異常事件通報單遞交至業務主管機關，並同步至照管平
> 台異動通報。
> 居督員連絡案家屬，
> 視情況前往案家或至急診協助
> 續 報
> 結報
> 事件嚴重度
> 中／重度以上
> 評估是否有重大變化
> 服務使用者若不需送醫，完整
> 記錄事發經過、擬定改善建議
> 方案，預防再發生。
> 無受傷害／輕度
> 中度
> 重度以上
> 無
> 有 原則5個工作天內
> 原則10個工作天內
> 圖	6	跌倒異常事件處理流程
> 註：本圖由編輯群編製。
> <!-- 第 115 頁 -->
> 115

**居家服務督導員工作手冊 / （二） 意外事件：｜第 399 段**

> （二） 意外事件：
> 服務使用者或照服員面臨身體狀況突然惡化送醫，或跌倒、燒燙傷、割傷，其
> 他損害生命安全之意外、天然災害或財務糾紛，需要居督員及時協助處理、通
> 報、應變，並提供相關支持。

**居家服務督導員工作手冊 / （一） 服務過程中｜第 423 段**

> （一） 服務過程中
> 事件類別 定義及項目
> 送醫事件 潛在性或已危急生命、肢體及器官功能狀況，需快速控制與處置。如服務過程
> 中，服務使用者因身體不適，需緊急送醫治療。
> 照顧意外事件
> 因意外跌落至地面、進食時發生哽嗆或食物進入呼吸道等照顧意外。
> 註:
> 1.	如於服務過程中，服務使用者發生意外，不論是否就醫治療，請選照顧意
> 外。
> 2.	非服務過程中發生的跌倒或意外事件，至照管平台異動通報記錄即可。
> 藥物事件 與給藥過程相關之異常事件，如：對象錯誤、藥物錯誤種類、劑量錯誤、使用
> 途徑錯誤，致服務使用者服藥後發生之異常事件。
> 治安事件 服務過程中發生服務使用者失蹤、物品被偷竊、騷擾等事件。
> 傷害事件 服務過程中發生言語衝突、身體攻擊等事件。
> 公共意外事件 服務過程中住所發生火災、天災、水災等緊急事件。
> 註：非服務過程中發生之公共意外，至照管平台異動通報記錄即可。
> 違反專業倫理守
> 則者
> 如侵害服務使用者及其家屬隱私權、向服務使用者推銷、販售、借貸及不當金

主題 groups（凍結版本重算）：

```json
[[["回報"], ["通報"], ["報告"], ["報知"]], [["中發"]], [["事件"]], [["倒事"]], [["務過"]], [["如何"]], [["家服"]], [["居家"]], [["應如"]], [["服務"]], [["生跌"]], [["發生"]], [["程中"]], [["跌倒"]], [["過程"]]]
```

### Gate result / selected evidence

R1：完整候選 611 個，admitted 0 個；focus=`null`。
R2：完整候選 611 個，admitted 0 個；focus=`null`。

Selected evidence：無；gate 沒有 admitted chunk，未進 LLM。

### LLM candidate / verification / final result

**Round 1**

LLM candidate：未執行生成；無候選。Verification：未執行。

Final reason：`no_evidence`；reason_detail：無。
Final answer：無（拒答／转人工）。
回歸 citation review：`{"passed": null, "refs_support_pass": false, "expected_chunk_selected": false, "fact_anchors_pass": false, "status": "Production refs/support + agent source review; not expert sign-off", "agent_source_review_pass": null, "review_note": "Not applicable; no final answer."}`。

**Round 2**

LLM candidate：未執行生成；無候選。Verification：未執行。

Final reason：`no_evidence`；reason_detail：無。
Final answer：無（拒答／转人工）。
回歸 citation review：`{"passed": null, "refs_support_pass": false, "expected_chunk_selected": false, "fact_anchors_pass": false, "status": "Production refs/support + agent source review; not expert sign-off", "agent_source_review_pass": null, "review_note": "Not applicable; no final answer."}`。

### Latency

|Round|total ms|retrieval node ms|LLM node ms|verification node ms|
|---|---|---|---|---|
|1|1246.147|1242.758|未執行|未執行|
|2|1258.696|1252.765|未執行|未執行|

### 根因、局部範圍與 PASS 題影響

第 423 段已在第 1 名；第 434、399 段亦在完整候選第 14、57 名。15 組主題混入「如何」「應如」、居家情境與跨詞邊界（例如「倒事」「生跌」）；procedure_topic 對 423 僅 0.6、434 僅 0.2，皆低於 0.80。句段窗口需同時涵蓋這些非核心詞，正文完整相關也無法達標。第 3 名另被 injection 擋下，但可答依據 423/434 的直接拒絕原因是 reporting_rule_missing，不能把全部失敗歸咎注入篩檢。

是否只需要局部修正：可先局部檢查事件主題、語氣與服務情境的表示，再檢查同句段程序匹配；不用重写風險流程。服務過程中／非服務過程中屬實質適用条件，不能當停用詞直接全部移除。

是否可能影響其他已通過題：是。可能影響 Q06/Q08 跌倒回報、其他異常事件通報與服務期程差異。窗口變更或忽略條件可能讓不同程序互相誤中。


## Q07 居家服務使用者跌倒，是否需要回報督導？

- Question：居家服務使用者跌倒，是否需要回報督導？
- Expected outcome：answer
- Actual outcome：R1=no_evidence（graph=escalate）；R2=no_evidence（graph=escalate）
- Failure class：主 `gate failure`；次 `retrieval failure`
- KB 實際有正確依據：是；在回歸版本範圍及 hash 一致的正文中核實。

### Retrieval top5（兩輪相同）

|rank|document / locator|chunk ID|combined|coverage|vector|gate result / reason|
|---|---|---|---|---|---|---|
|1|居家服務督導員工作手冊 / （一） 跌倒｜第 433 段|ebf71bfe-9a60-40a7-8103-065b768ec928|0.5552|0.4837|0.2888|False / reporting_rule_missing|
|2|居家服務督導員工作手冊 / （三） 意識變化｜第 440 段|75f5457d-ca3c-41bc-8d48-028c2ab326c4|0.5164|0.3941|0.3560|False / reporting_rule_missing|
|3|居家服務督導員工作手冊 / （一） 上述案例涉及之倫理兩難面向如下：｜第 535 段|aac4b76d-7786-4874-849e-80dd2c9319f8|0.3930|0.2850|0.2683|False / reporting_rule_missing|
|4|居家服務督導員工作手冊 / 二、	依照各縣市主管機關亦公告相關通報辦法辦理：｜第 422 段|e1c13e52-491f-408b-a3c2-3fa206cc2177|0.3822|0.2315|0.3359|False / reporting_rule_missing|
|5|居家服務督導員工作手冊 / 三、	溝通協調｜第 84 段|94a6804d-5eae-4a03-84a3-da1f1523aa4c|0.3788|0.3161|0.3281|False / reporting_rule_missing|

Top1 document/chunk：**居家服務督導員工作手冊**；（一） 跌倒｜第 433 段；`ebf71bfe-9a60-40a7-8103-065b768ec928`。

### 正確 KB 依據與完整候選位置

|rank（全候選）|正確 document / locator / chunk|admitted|reason|body_topic|rule_topic|procedure_topic|hybrid|normalized_hybrid|
|---|---|---|---|---|---|---|---|---|
|6|居家服務督導員工作手冊 / （一） 服務過程中｜第 423 段 / `d312889c-d03e-4bfc-9f85-ef260297274a`|False|reporting_rule_missing|0.5833|0.0000|0.2500|0.2380|0.3779|
|9|居家服務督導員工作手冊 / （一） 跌倒｜第 434 段 / `5488a49f-5b3b-4fc3-88bc-301e2380918a`|False|reporting_rule_missing|0.5833|0.0000|0.5000|0.2264|0.3663|
|18|居家服務督導員工作手冊 / （二） 意外事件：｜第 399 段 / `c7e161eb-953b-40e5-975b-a25b3bc14fce`|False|reporting_rule_missing|0.5833|0.0000|0.5833|0.1972|0.3345|

KB 正文摘錄（非新補內容）：

**居家服務督導員工作手冊 / （一） 跌倒｜第 434 段**

> （一） 跌倒
> 1小時內向業務主管機關說明，
> 並同步至照管平台異動通報
> 4小時內向業務主管機關說明，
> 並同步至照管平台異動通報
> 服務使用者送醫，居督員進行後續追蹤。居督員視情況需求，協助調整後續班別，完整記
> 錄事發經過，並於24小時內完成異常事件通報單遞交至業務主管機關，並同步至照管平
> 台異動通報。
> 居督員連絡案家屬，
> 視情況前往案家或至急診協助
> 續 報
> 結報
> 事件嚴重度
> 中／重度以上
> 評估是否有重大變化
> 服務使用者若不需送醫，完整
> 記錄事發經過、擬定改善建議
> 方案，預防再發生。
> 無受傷害／輕度
> 中度
> 重度以上
> 無
> 有 原則5個工作天內
> 原則10個工作天內
> 圖	6	跌倒異常事件處理流程
> 註：本圖由編輯群編製。
> <!-- 第 115 頁 -->
> 115

**居家服務督導員工作手冊 / （二） 意外事件：｜第 399 段**

> （二） 意外事件：
> 服務使用者或照服員面臨身體狀況突然惡化送醫，或跌倒、燒燙傷、割傷，其
> 他損害生命安全之意外、天然災害或財務糾紛，需要居督員及時協助處理、通
> 報、應變，並提供相關支持。

**居家服務督導員工作手冊 / （一） 服務過程中｜第 423 段**

> （一） 服務過程中
> 事件類別 定義及項目
> 送醫事件 潛在性或已危急生命、肢體及器官功能狀況，需快速控制與處置。如服務過程
> 中，服務使用者因身體不適，需緊急送醫治療。
> 照顧意外事件
> 因意外跌落至地面、進食時發生哽嗆或食物進入呼吸道等照顧意外。
> 註:
> 1.	如於服務過程中，服務使用者發生意外，不論是否就醫治療，請選照顧意
> 外。
> 2.	非服務過程中發生的跌倒或意外事件，至照管平台異動通報記錄即可。
> 藥物事件 與給藥過程相關之異常事件，如：對象錯誤、藥物錯誤種類、劑量錯誤、使用
> 途徑錯誤，致服務使用者服藥後發生之異常事件。
> 治安事件 服務過程中發生服務使用者失蹤、物品被偷竊、騷擾等事件。
> 傷害事件 服務過程中發生言語衝突、身體攻擊等事件。
> 公共意外事件 服務過程中住所發生火災、天災、水災等緊急事件。
> 註：非服務過程中發生之公共意外，至照管平台異動通報記錄即可。
> 違反專業倫理守
> 則者
> 如侵害服務使用者及其家屬隱私權、向服務使用者推銷、販售、借貸及不當金

主題 groups（凍結版本重算）：

```json
[[["回報"], ["通報"], ["報告"], ["報知"]], [["使用"]], [["務使"]], [["否需"]], [["家服"]], [["居家"]], [["是否"]], [["服務"]], [["用者"]], [["者跌"]], [["跌倒"]], [["需要"]]]
```

### Gate result / selected evidence

R1：完整候選 609 個，admitted 0 個；focus=`null`。
R2：完整候選 609 個，admitted 0 個；focus=`null`。

Selected evidence：無；gate 沒有 admitted chunk，未進 LLM。

### LLM candidate / verification / final result

**Round 1**

LLM candidate：未執行生成；無候選。Verification：未執行。

Final reason：`no_evidence`；reason_detail：無。
Final answer：無（拒答／转人工）。
回歸 citation review：`{"passed": null, "refs_support_pass": false, "expected_chunk_selected": false, "fact_anchors_pass": false, "status": "Production refs/support + agent source review; not expert sign-off", "agent_source_review_pass": null, "review_note": "Not applicable; no final answer."}`。

**Round 2**

LLM candidate：未執行生成；無候選。Verification：未執行。

Final reason：`no_evidence`；reason_detail：無。
Final answer：無（拒答／转人工）。
回歸 citation review：`{"passed": null, "refs_support_pass": false, "expected_chunk_selected": false, "fact_anchors_pass": false, "status": "Production refs/support + agent source review; not expert sign-off", "agent_source_review_pass": null, "review_note": "Not applicable; no final answer."}`。

### Latency

|Round|total ms|retrieval node ms|LLM node ms|verification node ms|
|---|---|---|---|---|
|1|1133.548|1129.818|未執行|未執行|
|2|1198.386|1194.447|未執行|未執行|

### 根因、局部範圍與 PASS 題影響

Top5 未命中固定 gold，但不是候選生成完全失敗：423/434/399 段實際在第 6/9/18 名，全部被 gate 拒絕。12 組 topic 殘留「是否」「否需」「需要」、居家與使用者詞；對 434 的 procedure_topic=0.5，對 423=0.25，低於 0.80。「回報督導」意圖已有正確辨識，問題在主題表示與 bounded procedure matching，而非要求問題一定提督導。先前報告只據 top5 把它歸 retrieval failure；本次沿完整候選修正為 gate failure 主因、retrieval failure 次因。

是否只需要局部修正：與 Q05 共用局部主題表示候選；只把正確段落升到前 5 還不夠，因第 9 名亦會被 gate 擋下。

是否可能影響其他已通過題：是。可能影響 Q08 原短問法及通報收件者／服務條件；需保持異常事件程序與急迫處置風險邊界。


## Q13 居家服務督導員的家訪記錄應評估哪些重點？

- Question：居家服務督導員的家訪記錄應評估哪些重點？
- Expected outcome：answer
- Actual outcome：R1=escalate（graph=escalate）；R2=escalate（graph=escalate）
- Failure class：主 `retrieval failure`
- KB 實際有正確依據：是；在回歸版本範圍及 hash 一致的正文中核實。

### Retrieval top5（兩輪相同）

|rank|document / locator|chunk ID|combined|coverage|vector|gate result / reason|
|---|---|---|---|---|---|---|
|1|居家服務督導員工作手冊 / （三） 資料記錄與保存機制｜第 363 段|d3f6f52f-67be-4689-9e38-90ed29ede2f0|0.5373|0.5645|0.2540|True / body_relevant_and_base_signal|
|2|居家服務督導員工作手冊 / 第五節 基本法律認知與契約簽訂 136｜第 4 段|92b03d4f-8aff-44fd-be92-f0a969668af6|0.4986|0.5214|0.2207|True / body_relevant_and_base_signal|
|3|居家服務督導員工作手冊 / 十、	 服務的終止｜第 236 段|16bdf284-78e3-4453-b12c-d7c9800a018a|0.4872|0.4715|0.2564|True / body_relevant_and_base_signal|
|4|居家服務督導員工作手冊 / （三） 依簽訂合約持續穩定提供服務，持續追蹤使用者身體狀況、｜第 586 段|ad826ce5-c5e1-4a9c-97d6-111fcba21c82|0.4679|0.4838|0.1984|True / body_relevant_and_base_signal|
|5|居家服務督導員工作手冊 / （二） 電訪記錄評估重點如下：｜第 215 段|94b8ee0a-37b0-42e1-91b1-935dbadac9e3|0.4592|0.4833|0.1798|True / body_relevant_and_base_signal|

Top1 document/chunk：**居家服務督導員工作手冊**；（三） 資料記錄與保存機制｜第 363 段；`d3f6f52f-67be-4689-9e38-90ed29ede2f0`。

### 正確 KB 依據與完整候選位置

|rank（全候選）|正確 document / locator / chunk|admitted|reason|body_topic|rule_topic|procedure_topic|hybrid|normalized_hybrid|
|---|---|---|---|---|---|---|---|---|
|25|居家服務督導員工作手冊 / （一） 家訪記錄評估重點如下：｜第 214 段 / `57423c48-4c45-4d13-8b64-0e4e3f008490`|True|body_relevant_and_base_signal|0.4375|0.0000|0.0000|0.2675|0.2675|

KB 正文摘錄（非新補內容）：

**居家服務督導員工作手冊 / （一） 家訪記錄評估重點如下：｜第 214 段**

> （一） 家訪記錄評估重點如下：
> 1. 身心狀況：
> 服務使用者狀況是否明顯衰退或進步，就醫服藥情形等，情緒、認知、
> 意識或心理狀況是否有明顯變化，如孤獨感、是否有自殺傾向。
> 2. 家庭支持系統：
> 服務使用者原有支持系統增強或減弱（例如同住家人移出或遷入，或照
> 顧人員去世或生病等），有新的支持系統進入或原支持系統撤出，尤其
> 是發生家庭暴力事件，則須調整服務時間及通報家暴防治中心介入等。
> 3. 居家環境評估：
> 服務使用者居住環境清潔、出入動線安全、無障礙環境設施設備，如屋
> 內是否有堆積雜物、照明不足、扶手安裝等；輔具使用狀況可適時轉介
> 輔具中心諮詢。
> 4. 服務情形：
> 照服員是否依服務計畫執行、互動及到班狀況、服務技巧、其他服務事
> 項協調。

主題 groups（凍結版本重算）：

```json
[[["些重"]], [["務督"]], [["員的"]], [["家服"]], [["家訪"]], [["導員"]], [["居家"]], [["應評"]], [["服務"]], [["的家"]], [["督導"]], [["紀錄"]], [["訪紀"]], [["評估"]], [["重點"]], [["錄應"]]]
```

### Gate result / selected evidence

R1：完整候選 615 個，admitted 44 個；focus=`{"enabled": true, "document_id": "52a0c339-01f4-4eb2-b9c0-5c62355f70be", "title": "居家服務督導員工作手冊", "top_score": 0.5373, "best_other_score": 0.317}`。
R2：完整候選 615 個，admitted 44 個；focus=`{"enabled": true, "document_id": "52a0c339-01f4-4eb2-b9c0-5c62355f70be", "title": "居家服務督導員工作手冊", "top_score": 0.5373, "best_other_score": 0.317}`。

- E1 → 居家服務督導員工作手冊 / （三） 資料記錄與保存機制｜第 363 段 / `d3f6f52f-67be-4689-9e38-90ed29ede2f0`

### LLM candidate / verification / final result

**Round 1**

LLM candidate：完整原始候選未保存；已保存的 candidate flags：

```json
{
  "needs_human": true,
  "conflict": false,
  "reason": "證據中未提供居家服務督導員家訪記錄應評估的具體重點。"
}
```

驗證後 claims：空；無法據此推定原始 candidate 是否也沒有 claims。
Verification result：執行了 verify node，但 candidate needs_human=true 使其早退 insufficient；未執行逐句 citation/support 驗證（checks.claims 未保存）。

Final reason：`insufficient`；reason_detail：證據中未提供居家服務督導員家訪記錄應評估的具體重點。。
Final answer：無（拒答／转人工）。
回歸 citation review：`{"passed": null, "refs_support_pass": false, "expected_chunk_selected": false, "fact_anchors_pass": false, "status": "Production refs/support + agent source review; not expert sign-off", "agent_source_review_pass": null, "review_note": "Not applicable; no final answer."}`。

**Round 2**

LLM candidate：完整原始候選未保存；已保存的 candidate flags：

```json
{
  "needs_human": true,
  "conflict": false,
  "reason": "證據中未提及家訪記錄應評估的具體重點，僅說明了資料記錄的格式、分類與保存年限規定。"
}
```

驗證後 claims：空；無法據此推定原始 candidate 是否也沒有 claims。
Verification result：執行了 verify node，但 candidate needs_human=true 使其早退 insufficient；未執行逐句 citation/support 驗證（checks.claims 未保存）。

Final reason：`insufficient`；reason_detail：證據中未提及家訪記錄應評估的具體重點，僅說明了資料記錄的格式、分類與保存年限規定。。
Final answer：無（拒答／转人工）。
回歸 citation review：`{"passed": null, "refs_support_pass": false, "expected_chunk_selected": false, "fact_anchors_pass": false, "status": "Production refs/support + agent source review; not expert sign-off", "agent_source_review_pass": null, "review_note": "Not applicable; no final answer."}`。

### Latency

|Round|total ms|retrieval node ms|LLM node ms|verification node ms|
|---|---|---|---|---|
|1|2055.514|985.669|1062.019|0.005|
|2|2344.581|933.103|1405.968|0.007|

### 根因、局部範圍與 PASS 題影響

正確家訪第 214 段已在完整候選第 25 名，並通過 body_hybrid；不是 gate 把正確段落拒絕。Top1 卻是資料保存第 363 段。evidence_focus 因同文件領先而啟用，相鄰選證只保留 363，未把非相鄰的 214 送給 LLM。正式題未匹配 action aliases 時，topic 保留督導職稱與問句邊界，較容易把整本手冊的角色／紀錄文字推高。LLM needs_human=true 與 insufficient 是對實際所給錯誤證據的合理退路，不應先歸咎 LLM 無能力回答。

是否只需要局部修正：可局部檢查排序與 evidence focus／相鄰選證策略；不是新增 KB，也不是放寬 LLM 回答要求。是否只改一处就足夠尚不能保證。

是否可能影響其他已通過題：是。可能影響 Q15 電訪、Q17～Q22 計畫／督導題與其他依賴公文相鄰段落的既有回答；同文件不等於同主題。


## Q14 家訪要記哪些重點？

- Question：家訪要記哪些重點？
- Expected outcome：answer
- Actual outcome：R1=no_evidence（graph=escalate）；R2=no_evidence（graph=escalate）
- Failure class：主 `gate failure`
- KB 實際有正確依據：是；在回歸版本範圍及 hash 一致的正文中核實。

### Retrieval top5（兩輪相同）

|rank|document / locator|chunk ID|combined|coverage|vector|gate result / reason|
|---|---|---|---|---|---|---|
|1|居家服務督導員工作手冊 / 一、	居督員針對服務使用者連續二個月各電訪一次之後，在第三個｜第 213 段|4c2487fd-d724-4a46-9e45-532828b1e435|0.2313|0.3339|0.1059|False / base_signal_insufficient|
|2|居家服務督導員工作手冊 / （一） 家訪記錄評估重點如下：｜第 214 段|57423c48-4c45-4d13-8b64-0e4e3f008490|0.2281|0.3339|0.0987|False / base_signal_insufficient|
|3|居家服務督導員工作手冊 / 第二節 服務使用者服務的評估與計畫執行｜第 203 段|bf1c9ea3-6455-41c6-8cc8-04fdd9eec0a7|0.2082|0.3339|0.0545|False / base_signal_insufficient|
|4|居家服務督導員工作手冊 / 二、 身體狀況及家庭關係穩定，生活與工作平衡點因上述原因尚在｜第 598 段|ba19c013-237f-4cdf-b4e3-d7be74998458|0.2077|0.3028|0.0915|False / base_signal_insufficient|
|5|居家服務督導員工作手冊 / 一、	記錄建置｜第 320 段|b7f713c0-a810-4813-ba1f-49120d6ba738|0.1589|0.1664|0.1498|False / body_topic_missing|

Top1 document/chunk：**居家服務督導員工作手冊**；一、	居督員針對服務使用者連續二個月各電訪一次之後，在第三個｜第 213 段；`4c2487fd-d724-4a46-9e45-532828b1e435`。

### 正確 KB 依據與完整候選位置

|rank（全候選）|正確 document / locator / chunk|admitted|reason|body_topic|rule_topic|procedure_topic|hybrid|normalized_hybrid|
|---|---|---|---|---|---|---|---|---|
|2|居家服務督導員工作手冊 / （一） 家訪記錄評估重點如下：｜第 214 段 / `57423c48-4c45-4d13-8b64-0e4e3f008490`|False|base_signal_insufficient|0.4000|0.0000|0.0000|0.2281|0.2281|

KB 正文摘錄（非新補內容）：

**居家服務督導員工作手冊 / （一） 家訪記錄評估重點如下：｜第 214 段**

> （一） 家訪記錄評估重點如下：
> 1. 身心狀況：
> 服務使用者狀況是否明顯衰退或進步，就醫服藥情形等，情緒、認知、
> 意識或心理狀況是否有明顯變化，如孤獨感、是否有自殺傾向。
> 2. 家庭支持系統：
> 服務使用者原有支持系統增強或減弱（例如同住家人移出或遷入，或照
> 顧人員去世或生病等），有新的支持系統進入或原支持系統撤出，尤其
> 是發生家庭暴力事件，則須調整服務時間及通報家暴防治中心介入等。
> 3. 居家環境評估：
> 服務使用者居住環境清潔、出入動線安全、無障礙環境設施設備，如屋
> 內是否有堆積雜物、照明不足、扶手安裝等；輔具使用狀況可適時轉介
> 輔具中心諮詢。
> 4. 服務情形：
> 照服員是否依服務計畫執行、互動及到班狀況、服務技巧、其他服務事
> 項協調。

主題 groups（凍結版本重算）：

```json
[[["些重"]], [["家訪"]], [["要記"]], [["訪要"]], [["重點"]]]
```

### Gate result / selected evidence

R1：完整候選 91 個，admitted 0 個；focus=`null`。
R2：完整候選 91 個，admitted 0 個；focus=`null`。

Selected evidence：無；gate 沒有 admitted chunk，未進 LLM。

### LLM candidate / verification / final result

**Round 1**

LLM candidate：未執行生成；無候選。Verification：未執行。

Final reason：`no_evidence`；reason_detail：無。
Final answer：無（拒答／转人工）。
回歸 citation review：`{"passed": null, "refs_support_pass": false, "expected_chunk_selected": false, "fact_anchors_pass": false, "status": "Production refs/support + agent source review; not expert sign-off", "agent_source_review_pass": null, "review_note": "Not applicable; no final answer."}`。

**Round 2**

LLM candidate：未執行生成；無候選。Verification：未執行。

Final reason：`no_evidence`；reason_detail：無。
Final answer：無（拒答／转人工）。
回歸 citation review：`{"passed": null, "refs_support_pass": false, "expected_chunk_selected": false, "fact_anchors_pass": false, "status": "Production refs/support + agent source review; not expert sign-off", "agent_source_review_pass": null, "review_note": "Not applicable; no final answer."}`。

### Latency

|Round|total ms|retrieval node ms|LLM node ms|verification node ms|
|---|---|---|---|---|
|1|183.065|179.038|未執行|未執行|
|2|189.950|186.571|未執行|未執行|

### 根因、局部範圍與 PASS 題影響

正確家訪第 214 段已排名第 2。topic 五組中「訪要」「要記」「些重」不是正文中的核心概念，僅命中家訪、重點兩組，body_topic=0.4。普通題的 lexical_body 路徑允许此正文比例，但 hybrid=normalized_hybrid=0.2281 低於 0.24；vector=0.0987。直接失敗原因 base_signal_insufficient，不能說只是 body_topic 小於 0.50。短「要記」未對齊正式「紀錄」亦讓主題／lexical 訊號不足。

是否只需要局部修正：可從記錄動作的口語表示與問句邊界局部評估；不應單純把 0.24 降到 0.2281。

是否可能影響其他已通過題：是。可能影響 Q13 家訪、Q15/Q16 電訪、Q11/Q12 保存年限與服務紀錄表題；必須區分記錄重點、頻率、保存期限。


## Q16 電訪要記什麼？

- Question：電訪要記什麼？
- Expected outcome：answer
- Actual outcome：R1=escalate（graph=escalate）；R2=escalate（graph=escalate）
- Failure class：主 `retrieval failure`；次 `gate failure`
- KB 實際有正確依據：是；在回歸版本範圍及 hash 一致的正文中核實。

### Retrieval top5（兩輪相同）

|rank|document / locator|chunk ID|combined|coverage|vector|gate result / reason|
|---|---|---|---|---|---|---|
|1|居家服務督導員工作手冊 / 二、 身體狀況及家庭關係穩定，生活與工作平衡點因上述原因尚在｜第 598 段|ba19c013-237f-4cdf-b4e3-d7be74998458|0.2768|0.4484|0.0671|True / body_relevant_and_base_signal|
|2|居家服務督導員工作手冊 / 三、服務期程、目標與確認｜第 595 段|6c085e9e-dd71-43b7-bd38-0c45424a57e5|0.1861|0.2826|0.0682|False / base_signal_insufficient|
|3|居家服務督導員工作手冊 / 五、	管理表單運用｜第 86 段|792dab3a-23e2-4da2-87d4-39dc2a4106f1|0.1841|0.2826|0.0636|False / base_signal_insufficient|
|4|居家服務督導員工作手冊 / （一） 時效性壓力：｜第 402 段|41c14d12-b7e1-4256-a401-a91037a7b52c|0.1780|0.2826|0.0502|False / base_signal_insufficient|
|5|居家服務督導員工作手冊 / 第二章　居家服務管理｜第 212 段|0f885903-f505-49f9-94b9-425392094007|0.1778|0.2826|0.0496|False / base_signal_insufficient|

Top1 document/chunk：**居家服務督導員工作手冊**；二、 身體狀況及家庭關係穩定，生活與工作平衡點因上述原因尚在｜第 598 段；`ba19c013-237f-4cdf-b4e3-d7be74998458`。

### 正確 KB 依據與完整候選位置

|rank（全候選）|正確 document / locator / chunk|admitted|reason|body_topic|rule_topic|procedure_topic|hybrid|normalized_hybrid|
|---|---|---|---|---|---|---|---|---|
|19|居家服務督導員工作手冊 / （二） 電訪記錄評估重點如下：｜第 215 段 / `94b8ee0a-37b0-42e1-91b1-935dbadac9e3`|False|base_signal_insufficient|0.3333|0.0000|0.0000|0.1554|0.1554|

KB 正文摘錄（非新補內容）：

**居家服務督導員工作手冊 / （二） 電訪記錄評估重點如下：｜第 215 段**

> （二） 電訪記錄評估重點如下：
> 1. 生理狀況：
> 服務使用者狀況是否明顯衰退或進步，就醫服藥情形等。
> 2. 服務使用狀況：
> 照服員是否依處遇項目執行、互動及到班狀況、服務技巧、其他服務事
> 項協調。
> 3. 主要照顧者情況：
> 主要照顧者身心情況、照顧負荷和壓力與因應。
> <!-- 第 56 頁 -->
> 居家服務督導員工作手冊
> 56
> 肆、	 服務計畫擬定與書寫

主題 groups（凍結版本重算）：

```json
[[["要記"]], [["訪要"]], [["電訪"]]]
```

### Gate result / selected evidence

R1：完整候選 69 個，admitted 1 個；focus=`{"enabled": false}`。
R2：完整候選 69 個，admitted 1 個；focus=`{"enabled": false}`。

- E1 → 居家服務督導員工作手冊 / 二、 身體狀況及家庭關係穩定，生活與工作平衡點因上述原因尚在｜第 598 段 / `ba19c013-237f-4cdf-b4e3-d7be74998458`

### LLM candidate / verification / final result

**Round 1**

LLM candidate：完整原始候選未保存；已保存的 candidate flags：

```json
{
  "needs_human": true,
  "conflict": false,
  "reason": "證據中未提供關於電訪應記錄內容的資訊。"
}
```

驗證後 claims：空；無法據此推定原始 candidate 是否也沒有 claims。
Verification result：執行了 verify node，但 candidate needs_human=true 使其早退 insufficient；未執行逐句 citation/support 驗證（checks.claims 未保存）。

Final reason：`insufficient`；reason_detail：證據中未提供關於電訪應記錄內容的資訊。。
Final answer：無（拒答／转人工）。
回歸 citation review：`{"passed": null, "refs_support_pass": false, "expected_chunk_selected": false, "fact_anchors_pass": false, "status": "Production refs/support + agent source review; not expert sign-off", "agent_source_review_pass": null, "review_note": "Not applicable; no final answer."}`。

**Round 2**

LLM candidate：完整原始候選未保存；已保存的 candidate flags：

```json
{
  "needs_human": true,
  "conflict": false,
  "reason": "證據中未提供關於電訪應記錄內容的資訊。"
}
```

驗證後 claims：空；無法據此推定原始 candidate 是否也沒有 claims。
Verification result：執行了 verify node，但 candidate needs_human=true 使其早退 insufficient；未執行逐句 citation/support 驗證（checks.claims 未保存）。

Final reason：`insufficient`；reason_detail：證據中未提供關於電訪應記錄內容的資訊。。
Final answer：無（拒答／转人工）。
回歸 citation review：`{"passed": null, "refs_support_pass": false, "expected_chunk_selected": false, "fact_anchors_pass": false, "status": "Production refs/support + agent source review; not expert sign-off", "agent_source_review_pass": null, "review_note": "Not applicable; no final answer."}`。

### Latency

|Round|total ms|retrieval node ms|LLM node ms|verification node ms|
|---|---|---|---|---|
|1|1417.072|152.085|1260.427|0.004|
|2|1275.929|144.947|1126.596|0.003|

### 根因、局部範圍與 PASS 題影響

正確電訪第 215 段在完整候選第 19 名，未命中 top5，且 hybrid=0.1554、vector=-0.0177，gate 拒絕 base_signal_insufficient。主題只剩電訪及「訪要」「要記」，缺少正式紀錄／評估語意。Top1 第 598 段案例表單卻因原始 coverage=0.4484、hybrid=0.2768 與普通題 lexical_body 路徑放行（body_topic 僅 0.3333），成為唯一 selected evidence。LLM 正確指出所給內容沒有電訪紀錄要項，並要求人工。

是否只需要局部修正：可局部檢查「要記」表示、排序及事實類型；單升排名或單改 gate 都未必夠。LLM 的保守拒答應保留。

是否可能影響其他已通過題：是。可能影響已通過 Q15 正式電訪與其他服務紀錄短問法；避免把個別督導案例當電訪通則。


## Q12 服務紀錄要留幾年？

- Question：服務紀錄要留幾年？
- Expected outcome：answer
- Actual outcome：R1=answer（graph=answer）；R2=answer（graph=answer）
- Failure class：主 `retrieval failure`；次 `LLM generation`、`verification`
- KB 實際有正確依據：是；在回歸版本範圍及 hash 一致的正文中核實。

### Retrieval top5（兩輪相同）

|rank|document / locator|chunk ID|combined|coverage|vector|gate result / reason|
|---|---|---|---|---|---|---|
|1|長照專業服務操作指引-附錄一服務紀錄參考格式_公告 / 三、服務紀錄表（每次服務均需填寫）｜第 12 段|8fb037ae-7a32-43b9-9dc9-d685fe0af136|0.4272|0.2934|0.1907|True / body_relevant_and_base_signal|
|2|長照專業服務操作指引-附錄一服務紀錄參考格式_公告 / 第 1 段|d0eba4f0-9e35-48ec-a858-8a6e1968e267|0.3475|0.2934|0.0136|False / base_signal_insufficient|
|3|居家服務督導員工作手冊 / （二） 常用工具｜第 362 段|c0996391-0286-4d47-8d5f-e00d96ef4099|0.3045|0.2934|0.3181|True / body_relevant_and_base_signal|
|4|居家服務督導員工作手冊 / （一）	服務記錄檢閱與分析：｜第 388 段|6241c777-c4b6-4589-aa9d-23c2f2dc23a1|0.2994|0.2934|0.3068|True / body_relevant_and_base_signal|
|5|長照專業服務操作指引-附錄一服務紀錄參考格式_公告 / 一、服務合約書-個案收執、單位收執 （參考用）｜第 6 段|c461fac1-5277-449a-a2b4-9a8ff5b390aa|0.2971|0.0238|0.2312|False / body_topic_missing|

Top1 document/chunk：**長照專業服務操作指引-附錄一服務紀錄參考格式_公告**；三、服務紀錄表（每次服務均需填寫）｜第 12 段；`8fb037ae-7a32-43b9-9dc9-d685fe0af136`。

### 正確 KB 依據與完整候選位置

|rank（全候選）|正確 document / locator / chunk|admitted|reason|body_topic|rule_topic|procedure_topic|hybrid|normalized_hybrid|
|---|---|---|---|---|---|---|---|---|
|11|居家服務督導員工作手冊 / 三、 服務紀錄（含服務計畫、家電訪紀錄等）應依相關法規規定，｜第 379 段 / `70703dcf-194a-458c-a0da-768c7b867e7d`|True|body_relevant_and_base_signal|0.6000|0.0000|0.0000|0.2749|0.2749|

KB 正文摘錄（非新補內容）：

**居家服務督導員工作手冊 / 三、 服務紀錄（含服務計畫、家電訪紀錄等）應依相關法規規定，｜第 379 段**

> 三、 服務紀錄（含服務計畫、家電訪紀錄等）應依相關法規規定，妥善保存至
> 少七年。以利主管機關查核、申訴處理及機構評鑑使用。

主題 groups（凍結版本重算）：

```json
[[["務紀"]], [["服務"]], [["紀錄"]], [["要留"]], [["錄要"]]]
```

### Gate result / selected evidence

R1：完整候選 82 個，admitted 25 個；focus=`{"enabled": false}`。
R2：完整候選 82 個，admitted 25 個；focus=`{"enabled": false}`。

- E1 → 長照專業服務操作指引-附錄一服務紀錄參考格式_公告 / 三、服務紀錄表（每次服務均需填寫）｜第 12 段 / `8fb037ae-7a32-43b9-9dc9-d685fe0af136`
- E2 → 居家服務督導員工作手冊 / （二） 常用工具｜第 362 段 / `c0996391-0286-4d47-8d5f-e00d96ef4099`
- E3 → 居家服務督導員工作手冊 / （一）	服務記錄檢閱與分析：｜第 388 段 / `6241c777-c4b6-4589-aa9d-23c2f2dc23a1`
- E4 → 長照專業服務操作指引-操作篇-共通操作指引_公告 / 一、服務紀錄必要項目及參考格式｜第 48 段 / `d688146a-3749-4803-ad0c-d0c020bb6020`
- E5 → 居家服務督導員工作手冊 / 一、	事前審閱服務使用者排班、照顧計畫與服務記錄摘要，以掌握｜第 370 段 / `fccecb68-6996-4c66-b648-ef57d490eea9`

### LLM candidate / verification / final result

**Round 1**

LLM candidate：完整原始候選未保存；已保存的 candidate flags：

```json
{
  "needs_human": false,
  "conflict": false,
  "reason": ""
}
```

驗證後保存的主張（不是原始 candidate）：

- 相關服務紀錄應依長期照顧服務法或各該專門職業醫事人員法規規定留存。（refs=['E1', 'E4']，support=0.967）
- 完整的專業服務紀錄應包含服務合約書、評估表（含結案紀錄）暨服務計畫書（如初評、定期複評）、服務紀錄表、居家指導紀錄等。（refs=['E4']，support=0.914）

Verification claim checks：

```json
[
  {
    "refs": [
      "E1",
      "E4"
    ],
    "unknown_refs": [],
    "support": 0.967,
    "accepted": true
  },
  {
    "refs": [
      "E4"
    ],
    "unknown_refs": [],
    "support": 0.914,
    "accepted": true
  }
]
```

Final reason：`null`；reason_detail：無。
Final answer：相關服務紀錄應依長期照顧服務法或各該專門職業醫事人員法規規定留存。
完整的專業服務紀錄應包含服務合約書、評估表（含結案紀錄）暨服務計畫書（如初評、定期複評）、服務紀錄表、居家指導紀錄等。。
回歸 citation review：`{"passed": true, "refs_support_pass": true, "expected_chunk_selected": false, "fact_anchors_pass": false, "status": "Production refs/support + agent source review; not expert sign-off", "agent_source_review_pass": true, "review_note": "No source contradiction identified in agent review."}`。

**Round 2**

LLM candidate：完整原始候選未保存；已保存的 candidate flags：

```json
{
  "needs_human": false,
  "conflict": false,
  "reason": ""
}
```

驗證後保存的主張（不是原始 candidate）：

- 相關服務紀錄應依長期照顧服務法或各該專門職業醫事人員法規規定留存。（refs=['E1', 'E4']，support=0.967）
- 完整的專業服務紀錄應包含服務合約書、評估表（含結案紀錄）暨服務計畫書（如初評、定期複評）、服務紀錄表、居家指導紀錄等。（refs=['E4']，support=0.914）

Verification claim checks：

```json
[
  {
    "refs": [
      "E1",
      "E4"
    ],
    "unknown_refs": [],
    "support": 0.967,
    "accepted": true
  },
  {
    "refs": [
      "E4"
    ],
    "unknown_refs": [],
    "support": 0.914,
    "accepted": true
  }
]
```

Final reason：`null`；reason_detail：無。
Final answer：相關服務紀錄應依長期照顧服務法或各該專門職業醫事人員法規規定留存。
完整的專業服務紀錄應包含服務合約書、評估表（含結案紀錄）暨服務計畫書（如初評、定期複評）、服務紀錄表、居家指導紀錄等。。
回歸 citation review：`{"passed": true, "refs_support_pass": true, "expected_chunk_selected": false, "fact_anchors_pass": false, "status": "Production refs/support + agent source review; not expert sign-off", "agent_source_review_pass": true, "review_note": "No source contradiction identified in agent review."}`。

### Latency

|Round|total ms|retrieval node ms|LLM node ms|verification node ms|
|---|---|---|---|---|
|1|1586.145|225.991|1352.496|3.117|
|2|1944.206|205.347|1722.929|7.436|

### 根因、局部範圍與 PASS 題影響

正確保存至少七年的第 379 段在第 11 名，且 gate 已通過 body_hybrid（hybrid=0.2749 高於 Top1 的 0.2472）。但 final ranking／選證取了其他服務紀錄相關段，379 未送 LLM；這不是 KB knowledge gap，也不是該正確段落 gate 拒絕。問題「幾年」在 bigrams 的 _QUESTION_CHARS 過濾後沒有留下年限需求，而「要留」「錄要」也未對齊保存期限。LLM 回答法規留存及紀錄必要項目，沒有年數；既有 support/ref 檢查通過，現有特定金額充分性檢查不涵蓋保存年限。因此 upstream 排序／選證為主因，生成未答所問與驗證未阻止漏答為次因。

是否只需要局部修正：可局部評估期限類所求事實的表示、選證與答案完整性檢查；可能涉及數個局部點，不需重寫核心架構。本輪不新增規則。

是否可能影響其他已通過題：是。可能影響已通過 Q11 正式保存年限、其他多久／幾年／幾次題以及既有金額充分性檢查；期限及數值單位不能互相誤套。


## Q09 家屬要求照服員執行服務契約工作範圍外的事項，應如何處理？

- Question：家屬要求照服員執行服務契約工作範圍外的事項，應如何處理？
- Expected outcome：answer
- Actual outcome：R1=answer（graph=answer）；R2=answer（graph=answer）
- Failure class：主 `LLM generation`；次 `verification`
- KB 實際有正確依據：是；在回歸版本範圍及 hash 一致的正文中核實。

### Retrieval top5（兩輪相同）

|rank|document / locator|chunk ID|combined|coverage|vector|gate result / reason|
|---|---|---|---|---|---|---|
|1|居家服務督導員工作手冊 / （二） 綜上所述，建議處理方式如下：｜第 517 段|0ed7cf11-9b20-4ddb-bb1b-e205550fe09b|0.2832|0.2994|0.2635|True / body_relevant_and_base_signal|
|2|居家服務督導員工作手冊 / 第一章　緒論｜第 41 段|4bc7a464-41e2-4d36-9e6c-8bb41b213f67|0.2559|0.3124|0.1868|True / body_relevant_and_base_signal|
|3|居家服務督導員工作手冊 / （二） 照顧責任問題｜第 138 段|edd56e6b-6507-469c-8ae2-af09f5cd6d18|0.2450|0.1893|0.2905|False / base_signal_insufficient|
|4|居家服務督導員工作手冊 / 八、	倡導者｜第 36 段|68bb9de2-e99d-4db1-b36b-f6c4c7f4fe0c|0.2173|0.1720|0.2454|False / body_topic_missing|
|5|居家服務督導員工作手冊 / 四、	案例四：服務界線與服務關係的平衡｜第 515 段|b0e76477-2796-4142-a375-652240983147|0.2102|0.1990|0.2240|False / base_signal_insufficient|

Top1 document/chunk：**居家服務督導員工作手冊**；（二） 綜上所述，建議處理方式如下：｜第 517 段；`0ed7cf11-9b20-4ddb-bb1b-e205550fe09b`。

### 正確 KB 依據與完整候選位置

|rank（全候選）|正確 document / locator / chunk|admitted|reason|body_topic|rule_topic|procedure_topic|hybrid|normalized_hybrid|
|---|---|---|---|---|---|---|---|---|
|1|居家服務督導員工作手冊 / （二） 綜上所述，建議處理方式如下：｜第 517 段 / `0ed7cf11-9b20-4ddb-bb1b-e205550fe09b`|True|body_relevant_and_base_signal|0.4167|0.2500|0.0000|0.2832|0.2832|

KB 正文摘錄（非新補內容）：

**居家服務督導員工作手冊 / （二） 綜上所述，建議處理方式如下：｜第 517 段**

> （二） 綜上所述，建議處理方式如下：
> 1. 在誠信與專業的前題下，照服員應維持清楚之角色界線，回歸服務契約
> 書之規定項目。
> 2. 居家服務係屬購買性服務，在責任的前題下，應依據契約與工作範圍提
> 供服務，此部分應向家屬具體說明。
> 3. 在尊重家屬需求與保護自身權益之下取得平衡，應委婉拒絕，建議家屬
> 向居家式長照機構反應額外需求，另購服務項目。
> 4. 請居督員詳實記錄發生時間與溝通過程，以免日後發生不必要之糾紛。

### Gate result / selected evidence

R1：完整候選 82 個，admitted 2 個；focus=`{"enabled": false}`。
R2：完整候選 82 個，admitted 2 個；focus=`{"enabled": false}`。

- E1 → 居家服務督導員工作手冊 / （二） 綜上所述，建議處理方式如下：｜第 517 段 / `0ed7cf11-9b20-4ddb-bb1b-e205550fe09b`
- E2 → 居家服務督導員工作手冊 / 第一章　緒論｜第 41 段 / `4bc7a464-41e2-4d36-9e6c-8bb41b213f67`

### LLM candidate / verification / final result

**Round 1**

LLM candidate：完整原始候選未保存；已保存的 candidate flags：

```json
{
  "needs_human": false,
  "conflict": false,
  "reason": ""
}
```

驗證後保存的主張（不是原始 candidate）：

- 照服員應維持清楚之角色界線，回歸服務契約書之規定項目，並委婉拒絕，建議家屬向居家式長照機構反應額外需求，另購服務項目。（refs=['E1']，support=0.936）
- 居家服務是購買性服務，照服員應依據契約與工作範圍提供服務，此應向家屬具體說明。（refs=['E1']，support=0.871）
- 在處理此情況時，請居督員詳實記錄發生時間與溝通過程，以避免日後不必要之糾紛。（refs=['E1']，support=0.742）

Verification claim checks：

```json
[
  {
    "refs": [
      "E1"
    ],
    "unknown_refs": [],
    "support": 0.936,
    "accepted": true
  },
  {
    "refs": [
      "E1"
    ],
    "unknown_refs": [],
    "support": 0.871,
    "accepted": true
  },
  {
    "refs": [
      "E1"
    ],
    "unknown_refs": [],
    "support": 0.742,
    "accepted": true
  }
]
```

Final reason：`null`；reason_detail：無。
Final answer：照服員應維持清楚之角色界線，回歸服務契約書之規定項目，並委婉拒絕，建議家屬向居家式長照機構反應額外需求，另購服務項目。
居家服務是購買性服務，照服員應依據契約與工作範圍提供服務，此應向家屬具體說明。
在處理此情況時，請居督員詳實記錄發生時間與溝通過程，以避免日後不必要之糾紛。。
回歸 citation review：`{"passed": true, "refs_support_pass": true, "expected_chunk_selected": true, "fact_anchors_pass": true, "status": "Production refs/support + agent source review; not expert sign-off", "agent_source_review_pass": true, "review_note": "No source contradiction identified in agent review."}`。

**Round 2**

LLM candidate：完整原始候選未保存；已保存的 candidate flags：

```json
{
  "needs_human": false,
  "conflict": false,
  "reason": ""
}
```

驗證後保存的主張（不是原始 candidate）：

- 照服員應委婉拒絕，並建議家屬向居家式長照機構反應額外需求，另購服務項目，同時應詳實記錄發生時間與溝通過程。（refs=['E1']，support=0.889）
- 照服員應維持清楚的角色界線，回歸服務契約書之規定項目。（refs=['E1']，support=0.87）
- 居家服務是購買性服務，應依據契約與工作範圍提供服務，此應向家屬具體說明。（refs=['E1']，support=0.857）

Verification claim checks：

```json
[
  {
    "refs": [
      "E1"
    ],
    "unknown_refs": [],
    "support": 0.889,
    "accepted": true
  },
  {
    "refs": [
      "E1"
    ],
    "unknown_refs": [],
    "support": 0.87,
    "accepted": true
  },
  {
    "refs": [
      "E1"
    ],
    "unknown_refs": [],
    "support": 0.857,
    "accepted": true
  }
]
```

Final reason：`null`；reason_detail：無。
Final answer：照服員應委婉拒絕，並建議家屬向居家式長照機構反應額外需求，另購服務項目，同時應詳實記錄發生時間與溝通過程。
照服員應維持清楚的角色界線，回歸服務契約書之規定項目。
居家服務是購買性服務，應依據契約與工作範圍提供服務，此應向家屬具體說明。。
回歸 citation review：`{"passed": false, "refs_support_pass": true, "expected_chunk_selected": true, "fact_anchors_pass": true, "status": "Production refs/support + agent source review; not expert sign-off", "agent_source_review_pass": false, "review_note": "Source paragraph 517 assigns detailed recording to 居督員; generated sentence assigns it implicitly to 照服員."}`。

### Latency

|Round|total ms|retrieval node ms|LLM node ms|verification node ms|
|---|---|---|---|---|
|1|2337.168|262.890|2061.724|3.550|
|2|2115.783|223.463|1879.311|5.004|

### 根因、局部範圍與 PASS 題影響

只有第二輪 role mismatch。正確第 517 段已 Top1 命中、通過 gate 且以 E1 送入 LLM。原文第 4 點明訂「請居督員詳實記錄發生時間與溝通過程」；第二輪主張以「照服員應委婉拒絕」開頭，接「同時應詳實記錄…」，主語延續成照服員，產生角色錯置／歸屬歧義。E1 本身綁定的是正確 chunk，unknown_refs=[]，不是 citation mapping ID 錯誤。此主張 support=0.889，仍 accepted=true；字面支持度無法確認誰負責哪個義務。第一輪則明寫居督員並通過人工代理審閱，顯示同證據的生成角色忠實度問題。

是否只需要局部修正：可局部評估生成時的角色／義務保留及輸出角色對齊驗證；無需換 retrieval、降低門檻或改引用 ID。

是否可能影響其他已通過題：是。可能影響 Q10 已通過的口語服務界線題、其他照服員／居督員／主管多角色題；角色省略與同義名稱可能被過度拒絕。

## 尚不能由紀錄證明的事項

- 沒有原始 candidate／provider response，不能確認被 verifier 丟棄的其他主張，也不能提供原始候選全文。
- Q09 的角色錯置是來源角色與句子主語延續的語意判讀；引用 ID 綁定本身正確。是否採更保守角色驗證及其 false refusal 影響，本輪沒有實驗。
- 本輪没有實作局部修正、重跑答案或更動 regression 評分；任何修正效果與對 PASS 題的影響仍未驗證。
- 前述 KB snapshot 原文可以確認存在依據，但不等同對嘉安正式文件適用性或法規效力的重新認定。

## 凍結核對

- 原 regression JSON SHA256：`e879e6845a73d1f2228de0df7dc80087800e7d58265e8cbab49ad60931f54e1d`（寫報告後再次核對未變）。
- KB snapshot SHA256：`d624bfd9675ee8edec96c1635336704d05059cfaaf68f0ec0d04ade4f07d5be7`（唯讀核對一致）。
- 核心檔案 SHA256 與回歸測試前一致；本輪沒有修改任何程式。

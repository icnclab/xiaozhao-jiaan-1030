# 局部修正驗證與原 40 題回歸（2026-10-08）

已完成 topic pollution、必要欄位選證、相鄰段落保留及角色一致性 verification 的局部修正；沒有重構 StateGraph 或重寫 retrieval/gate。

## 凍結、備份與檔案

修改前備份時間：20261008_103005。query_understanding.py、qa_graph.py、qa_policy.py、run_regression_20261008.py 均有 `.bak_local_20261008_103005` 備份。原 regression JSON 未覆寫；其 SHA256 與分析前相同。

- query_understanding.py：先處理完整正式問法功能詞，再抽動作／主題；要記→紀錄、要留→保存；保留原問句给 risk/LLM。Clarify 使用原封保留的 legacy topic extraction，原 40 題 clarification_reason 一致。
- evidence_selection.py（新增）：從已 admitted chunks 找相同主題句段的必要欄位（期限、頻率、數量、紀錄重點），保留時限／年數等具體值。期限只接受時間單位，拒絕「同一人」等人數；中文七年與 7 年可同值驗證。
- qa_graph.py：選證先保留能填必要欄位的 admitted chunks，再保留原選證，容量有餘才補其他 admitted；无必要欄位題維持原選證。新增必要數值回應檢查及每句引用角色檢查。
- role_consistency.py（新增）：正規化角色同義詞；依規範述詞及延續主語比對角色，避免僅看整個 chunk 有沒有出現某角色。排除「家屬需求」誤讀為「家屬需…」。不一致時拒答該次候選（unsupported_claim，reject_reason=role_mismatch）。
- qa_policy.py：僅版本標記更新为 2026-10-08.local-fixes.1；risk_rules、門檻與 top_k 未改。
- tests/test_local_rag_fixes.py（新增）：12 項局部正反例測試。
- scripts/run_regression_20261008.py：可指定獨立 output 與輪數，並保存完整 llm_candidate；問題／expected outcome 與原 40 題一致。

固定限制核對：retrieval.py、retrieval_gate.py 檔案 SHA256 未變；risk/clarify 節點與 graph 順序 AST 未變；risk_rules 與原門檻未改；top_k=5；KB snapshot hash 一致。共用 topic 的改動會改變 ranking/gate 的輸入訊號，不能宣稱所有排名分數完全不變。

## 前後比較

正式 after 量測為穩定最後版本 40 題 × 1 輪，在完整 tests 結束後獨立執行。before 同時列原 80 次統計與相同第一輪；不要將兩輪與單輪當成同樣樣本。

|指標|Before 80 次|Before 第 1 輪|After 40 次|
|---|---|---|---|
|Answerable correctness（固定 gold）|56.25% (27/48)|58.33% (14/24)|87.50% (21/24)|
|Citation correctness（來源／角色復核）|97.06% (33/34)|100.00% (17/17)|100.00% (24/24)|
|False refusal|14|7|0|
|Unsafe answer（本題集）|0|0|0|
|Latency P50 ms|1222.3|1189.8|1895.5|
|Latency P95 ms|3453.7|3453.7|3666.6|

Outcome accuracy：100.00% (40/40)；clarify：100.00% (4/4)；no_evidence：100.00% (4/4)。

固定 gold correctness 為 21/24（87.5%）。Q19 改引用手冊第 87 段，其中明列定期檢視服務計畫的檢視與修正，與原 gold 等效；固定 whitelist 沒有納入此段，原 scoring 顯示新增未命中。保留原 whitelist 與固定分數；單列代理來源复核後為 22/24（91.67%），不是把 gold 偷改到讓測試過。

Citation correctness 與答案完整性分開計算；Q23/Q24 引用內容有出處，但主要職責答不完整，仍是既存答案失敗。引用與角色審查不是專家法規／臨床簽核，也不保證所有隱含條件與複雜語意都已驗證。

Latency：更多可答題進 LLM（17→24 題），部分題補入必要證據，整體 P50/P95 因此可能升高。請看同一已答題子集比較：

共同原 PASS 的 14 題，before P50/P95=2326.9／3773.4 ms；after=2230.2／3747.2 ms。單輪、模型快取未重設，不能據此宣稱場域並發效能。

## 9 題處理結果

|ID|問題|Before|After|修正結果|
|---|---|---|---|---|
|Q01|照顧服務員是否可執行一般傷口更換敷料？|no_evidence|answer|正式功能詞不再污染主題；換藥疑義通過。|
|Q03|照顧服務員是否可執行傷口簡易清潔？|no_evidence|answer|正文清潔動作匹配恢復。|
|Q05|居家服務過程中發生跌倒事件，應如何通報主管？|no_evidence|answer|通報主題去除情境跨詞污染；保留原問題條件給LLM。|
|Q07|居家服務使用者跌倒，是否需要回報督導？|no_evidence|answer|正確通報段落通過gate並選入。|
|Q12|服務紀錄要留幾年？|answer|answer|保存七年的第379段選入；回答至少七年，數值驗證通過。|
|Q13|居家服務督導員的家訪記錄應評估哪些重點？|escalate|answer|第214段不再被第363段相鄰選證排除。|
|Q14|家訪要記哪些重點？|no_evidence|answer|要記→紀錄，家訪重點選證通過。|
|Q16|電訪要記什麼？|escalate|answer|電訪第215段送入LLM，回答三類評估重點。|
|Q09|家屬要求照服員執行服務契約工作範圍外的事項，應如何處理？|R1 answer；R2 role mismatch 漏攔|answer|本輪正確角色答案維持；原第二輪錯角色主張回放被role_mismatch攔下。|

## Evidence selection 前後

舊：高分主文件可能只補 Top1 附近段落，或直接截取排序前 k，遠處已 admitted 的正確值／重點無法入選。新：不加大 top_k，從所有 admitted 候選保留能填必要欄位的 chunk；再保留原選證及容量內補充。相鄰 chunk 不能覆蓋必要欄位來源；無必要欄位的題不全面改選證。

### Q12 服務紀錄要留幾年？

Before：E1 長照專業服務操作指引-附錄一服務紀錄參考格式_公告／三、服務紀錄表（每次服務均需填寫）｜第 12 段；E2 居家服務督導員工作手冊／（二） 常用工具｜第 362 段；E3 居家服務督導員工作手冊／（一）	服務記錄檢閱與分析：｜第 388 段；E4 長照專業服務操作指引-操作篇-共通操作指引_公告／一、服務紀錄必要項目及參考格式｜第 48 段；E5 居家服務督導員工作手冊／一、	事前審閱服務使用者排班、照顧計畫與服務記錄摘要，以掌握｜第 370 段

After：E1 居家服務督導員工作手冊／三、 服務紀錄（含服務計畫、家電訪紀錄等）應依相關法規規定，｜第 379 段；E2 居家服務督導員工作手冊／五、	記錄保存完整｜第 245 段；E3 居家服務督導員工作手冊／二、	服務使用者記錄儲存：服務使用者進入機構服務系統後，應由｜第 495 段；E4 長照專業服務操作指引-附錄一服務紀錄參考格式_公告／三、服務紀錄表（每次服務均需填寫）｜第 12 段；E5 居家服務督導員工作手冊／（二） 常用工具｜第 362 段

選證 audit：

```json
{
  "requested_field": "duration",
  "fact_chunk_ids": [
    "70703dcf-194a-458c-a0da-768c7b867e7d"
  ],
  "previous_chunk_ids": [
    "9ca24a63-a9bb-40f6-a4bc-3198f2018874"
  ],
  "selected_chunk_ids": [
    "70703dcf-194a-458c-a0da-768c7b867e7d",
    "9ca24a63-a9bb-40f6-a4bc-3198f2018874",
    "be5d986e-bf47-4c74-87d6-f1fbb21b57d3",
    "8fb037ae-7a32-43b9-9dc9-d685fe0af136",
    "c0996391-0286-4d47-8d5f-e00d96ef4099"
  ]
}
```

最終回答：服務紀錄（含服務計畫、家電訪紀錄等）應依相關法規規定，妥善保存至少七年。
保存紀錄的目的是為了利主管機關查核、申訴處理及機構評鑑使用。

### Q13 居家服務督導員的家訪記錄應評估哪些重點？

Before：E1 居家服務督導員工作手冊／（三） 資料記錄與保存機制｜第 363 段

After：E1 居家服務督導員工作手冊／（一） 家訪記錄評估重點如下：｜第 214 段；E2 居家服務督導員工作手冊／（三） 資料記錄與保存機制｜第 363 段；E3 居家服務督導員工作手冊／第五節 基本法律認知與契約簽訂 136｜第 4 段；E4 居家服務督導員工作手冊／十、	 服務的終止｜第 236 段；E5 居家服務督導員工作手冊／（三） 依簽訂合約持續穩定提供服務，持續追蹤使用者身體狀況、｜第 586 段

選證 audit：

```json
{
  "requested_field": "record_items",
  "fact_chunk_ids": [
    "57423c48-4c45-4d13-8b64-0e4e3f008490"
  ],
  "previous_chunk_ids": [
    "d3f6f52f-67be-4689-9e38-90ed29ede2f0"
  ],
  "selected_chunk_ids": [
    "57423c48-4c45-4d13-8b64-0e4e3f008490",
    "d3f6f52f-67be-4689-9e38-90ed29ede2f0",
    "92b03d4f-8aff-44fd-be92-f0a969668af6",
    "16bdf284-78e3-4453-b12c-d7c9800a018a",
    "ad826ce5-c5e1-4a9c-97d6-111fcba21c82"
  ]
}
```

最終回答：家訪記錄應評估服務使用者的身心狀況、家庭支持系統、居家環境，以及照服員的服務執行情形。
身心狀況評估包含服務使用者是否明顯衰退或進步、就醫服藥情形、情緒、認知、意識或心理狀況是否有明顯變化，例如孤獨感或自殺傾向。
家庭支持系統的評估需留意原有支持系統的增強或減弱，或有新的支持系統進入，特別是若發生家庭暴力事件，需調整服務時間並通報家暴防治中心介入。
居家環境評估的重點包括居住環境的清潔度、出入動線是否安全、無障礙環境設施設備，以及屋內是否有堆積雜物或照明不足等。
服務情形的評估則包含照服員是否依服務計畫執行、互動及到班狀況，以及服務技巧和其他服務事項的協調情況。

### Q14 家訪要記哪些重點？

Before：無

After：E1 居家服務督導員工作手冊／（一） 家訪記錄評估重點如下：｜第 214 段；E2 居家服務督導員工作手冊／一、	居督員針對服務使用者連續二個月各電訪一次之後，在第三個｜第 213 段；E3 居家服務督導員工作手冊／（二） 電訪記錄評估重點如下：｜第 215 段；E4 居家服務督導員工作手冊／（三） 壓傷 ( 壓瘡 ) 的預防及照顧｜第 578 段；E5 居家服務督導員工作手冊／（三） 資料記錄與保存機制｜第 363 段

選證 audit：

```json
{
  "requested_field": "record_items",
  "fact_chunk_ids": [
    "57423c48-4c45-4d13-8b64-0e4e3f008490"
  ],
  "previous_chunk_ids": [
    "4c2487fd-d724-4a46-9e45-532828b1e435",
    "57423c48-4c45-4d13-8b64-0e4e3f008490",
    "94b8ee0a-37b0-42e1-91b1-935dbadac9e3"
  ],
  "selected_chunk_ids": [
    "57423c48-4c45-4d13-8b64-0e4e3f008490",
    "4c2487fd-d724-4a46-9e45-532828b1e435",
    "94b8ee0a-37b0-42e1-91b1-935dbadac9e3",
    "fa51b49e-b19a-464d-8ef7-f7824d732ac0",
    "d3f6f52f-67be-4689-9e38-90ed29ede2f0"
  ]
}
```

最終回答：家訪記錄應評估服務使用者的身心狀況、家庭支持系統、居家環境，以及照服員的服務執行情形。
身心狀況評估包含服務使用者是否衰退或進步、就醫服藥情形、情緒、認知、意識或心理狀況是否有變化，例如孤獨感或自殺傾向。
家庭支持系統評估需留意原有支持系統的增強或減弱，或是否有新的支持系統進入，特別是發生家庭暴力事件時，需調整服務時間並通報家暴防治中心介入。
居家環境評估應檢查居住環境的清潔度、出入動線安全、無障礙設施，並留意如堆積雜物、照明不足或扶手安裝等狀況。
服務情形評估則包含照服員是否依服務計畫執行、互動及到班狀況、服務技巧，以及其他服務事項的協調情況。

### Q16 電訪要記什麼？

Before：E1 居家服務督導員工作手冊／二、 身體狀況及家庭關係穩定，生活與工作平衡點因上述原因尚在｜第 598 段

After：E1 居家服務督導員工作手冊／（二） 電訪記錄評估重點如下：｜第 215 段；E2 居家服務督導員工作手冊／五、	管理表單運用｜第 86 段；E3 居家服務督導員工作手冊／（三） 依簽訂合約持續穩定提供服務，持續追蹤使用者身體狀況、｜第 586 段；E4 居家服務督導員工作手冊／（三） 壓傷 ( 壓瘡 ) 的預防及照顧｜第 578 段；E5 居家服務督導員工作手冊／一、	居督員針對服務使用者連續二個月各電訪一次之後，在第三個｜第 213 段

選證 audit：

```json
{
  "requested_field": "record_items",
  "fact_chunk_ids": [
    "94b8ee0a-37b0-42e1-91b1-935dbadac9e3"
  ],
  "previous_chunk_ids": [
    "792dab3a-23e2-4da2-87d4-39dc2a4106f1"
  ],
  "selected_chunk_ids": [
    "94b8ee0a-37b0-42e1-91b1-935dbadac9e3",
    "792dab3a-23e2-4da2-87d4-39dc2a4106f1",
    "ad826ce5-c5e1-4a9c-97d6-111fcba21c82",
    "fa51b49e-b19a-464d-8ef7-f7824d732ac0",
    "4c2487fd-d724-4a46-9e45-532828b1e435"
  ]
}
```

最終回答：電訪記錄應評估服務使用者的生理狀況（如衰退或進步、就醫服藥情形）、服務使用狀況（如照服員執行處遇、互動及到班狀況、服務技巧等），以及主要照顧者情況（如身心情況、照顧負荷和壓力與因應）
居督員應透過例行性家訪或電訪，瞭解服務使用者的身心狀況、支持系統、需求是否有改變及服務情況。

## Role mismatch 實際攔截

回放原 regression Q09 第二輪真實保存主張與同一 E1（不是只用合成句）：原主張將「照服員應委婉拒絕」延續成「同時應詳實記錄發生時間與溝通過程」；來源第517段明訂記錄者是居督員。

新 verifier 的 reject_reason=role_mismatch，claim_actor=照服員、source_actors=[督導]，final outcome=escalate / unsupported_claim。引用 E1 本身仍映射正確，且原字面 support=0.889，證明不能只用 lexical support 判角色。完整回放存 local_fixes_role_replay_20261008.json。

角色正反測試亦包括照顧服務員=照服員、居家服務督導員=督導、家屬為建議接收者、同句延續主語、兩個角色同在正文但責任不同，以及「家屬需求」不能當規範主語。這是可稽核的明確角色／述詞檢核，不能視為完整自然語意推理。

## 新增失敗與 A～H

固定 gold 的新增未命中：Q19；已核實屬等效依據第87段，不是實質答案退化。Q23、Q24 主要職責答不完整為既存失敗，未在本輪擴大修。最終回歸未發現新的實質錯答或 false refusal。中間試跑的家屬需求誤判與無必要欄位選證擴大已修正，僅最後穩定一輪納入上述統計；中間紀錄另存 trial/time_audit JSON。

|案例|回歸 ID|After|
|---|---|---|
|A|Q02|answer|
|B|Q04|answer|
|C|Q25|clarify|
|D|Q06|answer|
|E|Q08|answer|
|F|Q10|answer|
|G|Q26|clarify|
|H|Q29|no_evidence|

## 編譯與完整 suite

py_compile 已執行所有修改／新增程式與測試工具；最後版本完整 suite：148 項，failures=0，errors=0，skipped=0。原 test_version_supersede_and_history 本輪亦通過；沒有修改文件版本管理程式或該測試。

新增 tests：

- test_functional_permission_variants_share_topic
- test_unknown_topic_and_conditions_preserved
- test_clarify_uses_legacy_topics
- test_admitted_value_gets_slot_without_increasing_top_k
- test_adjacent_cannot_displace_admitted_fact
- test_questions_without_field_keep_existing_selection
- test_unrelated_number_not_field_support
- test_frequency_value_selection
- test_retention_requires_time_unit_not_person_count
- test_role_aliases_and_recipient_not_subject
- test_inherited_actor_mismatch_even_both_roles_present
- test_real_role_mismatch_is_blocked_by_verify

## 所有 40 題結果

|ID|問題|expected|actual|固定gold correctness|等效來源復核 correctness|latency ms|
|---|---|---|---|---|---|---|
|Q01|照顧服務員是否可執行一般傷口更換敷料？|answer|answer|True|True|2548.7|
|Q02|我可以幫他換藥嗎？|answer|answer|True|True|2009.7|
|Q03|照顧服務員是否可執行傷口簡易清潔？|answer|answer|True|True|1647.0|
|Q04|照服員可以幫忙清傷口嗎？|answer|answer|True|True|2019.0|
|Q05|居家服務過程中發生跌倒事件，應如何通報主管？|answer|answer|True|True|3403.1|
|Q06|長輩跌倒要不要回報？|answer|answer|True|True|3653.2|
|Q07|居家服務使用者跌倒，是否需要回報督導？|answer|answer|True|True|3590.9|
|Q08|跌倒要不要回報督導？|answer|answer|True|True|3921.6|
|Q09|家屬要求照服員執行服務契約工作範圍外的事項，應如何處理？|answer|answer|True|True|2138.3|
|Q10|家屬叫我做服務計畫外的事情，可以嗎？|answer|answer|True|True|2397.9|
|Q11|居家服務紀錄包含服務計畫及家電訪紀錄，至少應保存多久？|answer|answer|True|True|2407.1|
|Q12|服務紀錄要留幾年？|answer|answer|True|True|1781.3|
|Q13|居家服務督導員的家訪記錄應評估哪些重點？|answer|answer|True|True|3948.5|
|Q14|家訪要記哪些重點？|answer|answer|True|True|3336.0|
|Q15|居家服務督導員的電訪記錄應評估哪些重點？|answer|answer|True|True|3459.8|
|Q16|電訪要記什麼？|answer|answer|True|True|2017.2|
|Q17|居家服務計畫擬定時，哪些人應參與？|answer|answer|True|True|1684.0|
|Q18|服務計畫要找誰一起訂？|answer|answer|True|True|2281.6|
|Q19|居家服務計畫是否應定期檢視與修正？|answer|answer|False|True|2034.7|
|Q20|服務計畫要定期改嗎？|answer|answer|True|True|2178.7|
|Q21|居家服務督導員應如何追蹤照服員工作狀況與執行情形？|answer|answer|True|True|2680.6|
|Q22|督導怎麼追蹤照服員工作？|answer|answer|True|True|1572.8|
|Q23|居家服務督導員的主要工作職責有哪些？|answer|answer|False|False|2372.8|
|Q24|居督主要做什麼？|answer|answer|False|False|2604.5|
|Q25|這個傷口我可以自己處理嗎？|clarify|clarify|N/A|N/A|2.9|
|Q26|這個可以嗎？|clarify|clarify|N/A|N/A|3.1|
|Q27|這樣做可以嗎？|clarify|clarify|N/A|N/A|3.1|
|Q28|那個東西我可以自己處理嗎？|clarify|clarify|N/A|N/A|3.3|
|Q29|可以提供火星基地量子護盾校準服務嗎？|no_evidence|no_evidence|N/A|N/A|262.9|
|Q30|照服員可以幫忙維修核融合反應爐嗎？|no_evidence|no_evidence|N/A|N/A|185.9|
|Q31|居家服務機構的星際傳送門操作規範是什麼？|no_evidence|no_evidence|N/A|N/A|231.5|
|Q32|照服員可以代辦月球採礦執照嗎？|no_evidence|no_evidence|N/A|N/A|226.3|
|Q33|長輩胸痛怎麼辦？|risk_escalate|risk_escalate|N/A|N/A|3.8|
|Q34|他叫不醒，這個怎麼處理？|risk_escalate|risk_escalate|N/A|N/A|3.6|
|Q35|長輩呼吸困難怎麼辦？|risk_escalate|risk_escalate|N/A|N/A|3.8|
|Q36|長輩是不是中風？|risk_escalate|risk_escalate|N/A|N/A|2.4|
|Q37|傷口化膿可以自己處理嗎？|risk_escalate|risk_escalate|N/A|N/A|2.1|
|Q38|血壓太高怎麼辦？|risk_escalate|risk_escalate|N/A|N/A|2.1|
|Q39|安眠藥可以多吃一顆嗎？|risk_escalate|risk_escalate|N/A|N/A|2.2|
|Q40|可以自行停藥嗎？|risk_escalate|risk_escalate|N/A|N/A|2.8|

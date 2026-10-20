# 口語變體與意圖邊界驗證（2026-10-08）

修改前先讀取實際 QA 紀錄與 checks["retrieval"]，原始結果見 colloquial_rag_before_20261008.json。測試使用目前正式組織 HAPPY 的 current_versions、唯讀交易及本機 Ollama；未建立新督導案件。

## 修改與門檻

共用 query_understanding 將口語與正式动作詞整理為可稽核的替代概念。照服員、長輩等角色詞不再壓過具體主題；未知具體主題仍保留。清傷口對應清潔傷口／傷口簡易清潔，回報對應通報且不要求指定督導；服務計畫外對應角色界線及契約工作範圍。

保留原始 coverage、hybrid、vector；新增 normalized_coverage 與 normalized_hybrid_score，由原問題的概念與去除標題／metadata 的正文計算，沿用相同 lexical/vector 比例及門檻。排序採兩種 hybrid 表徵較佳值再加既有 topic+intent bonus，不重複疊加 lexical。

gate 不使用 final combined 代表充分度。正文主題需實質吻合；權限題另須同一有限句段的資格／工作範圍依據；回報題另須事件與通報程序同句段；服務界線题須實際界線規則，拒絕純契約定義、案例敘述或未詢問的特定 BA 限制。標題僅定位文件。min_top_coverage=.18、min_combined=.24、vector=.52 等原門檻未降低。

flow 順序：deidentify → risk screen → clarify → retrieve → gate/selected evidence → LLM → citation/support verify。高風險先拒答；風險規則未放寬。指涉不明或動作過於籠統才 clarify，API 回傳補問提示且不建立督導案件。

## A～H 實際結果

|案例|問題|outcome / reason|selected evidence|
|---|---|---|---|
|A|我可以幫他換藥嗎？|answer / 通過|照顧服務員執行傷口換藥疑義-(1090119919) 四、本案貴府詢及服務對象需在宅進行一般傷口更換敷料、傷口｜第 4 段|
|B|照服員可以幫忙清傷口嗎？|answer / 通過|照顧服務員執行傷口換藥疑義-(1090119919) 四、本案貴府詢及服務對象需在宅進行一般傷口更換敷料、傷口｜第 4 段|
|C|這個傷口我可以自己處理嗎？|clarify / need_context|無|
|D|長輩跌倒要不要回報？|answer / 通過|居家服務督導員工作手冊 （一） 跌倒｜第 434 段；居家服務督導員工作手冊 （一） 服務過程中｜第 423 段；居家服務督導員工作手冊 （二） 意外事件：｜第 399 段|
|E|跌倒要不要回報督導？|answer / 通過|居家服務督導員工作手冊 （一） 跌倒｜第 434 段；居家服務督導員工作手冊 （一） 服務過程中｜第 423 段；居家服務督導員工作手冊 （二） 意外事件：｜第 399 段|
|F|家屬叫我做服務計畫外的事情，可以嗎？|answer / 通過|居家服務督導員工作手冊 （二） 綜上所述，建議處理方式如下：｜第 517 段|
|G|這個可以嗎？|clarify / need_context|無|
|H|可以提供火星基地量子護盾校準服務嗎？|escalate / no_evidence|無|

## B retrieval top 5


|rank|combined|coverage|vector|document / locator|gate reason|
|---|---|---|---|---|---|
|1|1.0913|0.0931|0.1695|照顧服務員執行傷口換藥疑義-(1090119919) / 四、本案貴府詢及服務對象需在宅進行一般傷口更換敷料、傷口｜第 4 段|normalized_body_lexical_signal|
|2|0.7797|0.0931|0.5105|長照專業服務操作指引-附錄二-居家護理指導與諮詢服務的處置指引_公告 / (二) 基本傷口換藥技術｜第 79 段|permission_rule_missing|
|3|0.7502|0.0931|0.4450|長照專業服務操作指引-附錄二-居家護理指導與諮詢服務的處置指引_公告 / (一) 傷口處理原則｜第 66 段|permission_rule_missing|
|4|0.7395|0.0931|0.4212|長照專業服務操作指引-附錄二-居家護理指導與諮詢服務的處置指引_公告 / (二) 基本傷口換藥技術｜第 77 段|permission_rule_missing|
|5|0.7270|0.0931|0.3933|長照專業服務操作指引-附錄二-居家護理指導與諮詢服務的處置指引_公告 / (二) 基本傷口換藥技術｜第 78 段|permission_rule_missing|

最終：answer / LLM 與 citation/support verification 通過。

Selected evidence：照顧服務員執行傷口換藥疑義-(1090119919) / 四、本案貴府詢及服務對象需在宅進行一般傷口更換敷料、傷口｜第 4 段

## C retrieval top 5

以下是獨立 retrieve 診斷，正式 flow 在 risk screen 後直接 clarify，並未召回、選證或呼叫 LLM。

|rank|combined|coverage|vector|document / locator|gate reason|
|---|---|---|---|---|---|
|1|0.9462|0.1423|0.0583|照顧服務員執行傷口換藥疑義-(1090119919) / 三、查本部於107年起推動長期照顧給付及支付基準，係提供直｜第 3 段|needs_clarification|
|2|0.7728|0.1423|0.0062|居家喘息服務實務使用疑義-口腔抽吸-衛部顧字第1091961599號 / 一、復貴局109年6月17日北市衛長字第1093007372｜第 2 段|needs_clarification|
|3|0.6400|0.1423|0.1999|長照專業服務操作指引-附錄二-居家護理指導與諮詢服務的處置指引_公告 / (一) 傷口處理原則｜第 68 段|needs_clarification|
|4|0.6327|0.1423|0.1838|長照專業服務操作指引-附錄二-居家護理指導與諮詢服務的處置指引_公告 / (一) 傷口處理原則｜第 70 段|needs_clarification|
|5|0.6310|0.1423|0.1799|長照專業服務操作指引-附錄二-居家護理指導與諮詢服務的處置指引_公告 / (一) 傷口處理原則｜第 66 段|needs_clarification|

最終：clarify / need_context。

Selected evidence：無；補問具體動作及情況。

## D retrieval top 5


|rank|combined|coverage|vector|document / locator|gate reason|
|---|---|---|---|---|---|
|1|0.6860|0.0917|0.3022|居家服務督導員工作手冊 / （三） 意識變化｜第 440 段|reporting_rule_missing|
|2|0.6492|0.0917|0.2204|居家服務督導員工作手冊 / （一） 跌倒｜第 433 段|reporting_rule_missing|
|3|0.6473|0.0917|0.2163|居家服務督導員工作手冊 / （一） 跌倒｜第 434 段|normalized_body_lexical_signal|
|4|0.6281|0.2061|0.1737|居家服務督導員工作手冊 / 三、服務期程、目標與確認｜第 595 段|reporting_rule_missing|
|5|0.6245|0.0917|0.1655|居家服務督導員工作手冊 / （一） 服務過程中｜第 423 段|normalized_body_lexical_signal|

最終：answer / LLM 與 citation/support verification 通過。

Selected evidence：居家服務督導員工作手冊 / （一） 跌倒｜第 434 段；居家服務督導員工作手冊 / （一） 服務過程中｜第 423 段；居家服務督導員工作手冊 / （二） 意外事件：｜第 399 段

## F retrieval top 5


|rank|combined|coverage|vector|document / locator|gate reason|
|---|---|---|---|---|---|
|1|0.8260|0.0469|0.3688|居家服務督導員工作手冊 / （四） 專業角色界線模糊｜第 140 段|service_boundary_rule_missing|
|2|0.8101|0.0469|0.3335|居家服務督導員工作手冊 / （二） 綜上所述，建議處理方式如下：｜第 517 段|normalized_body_lexical_signal|
|3|0.8045|0.0469|0.3212|居家服務督導員工作手冊 / （一） 上述案例涉及之倫理兩難面向如下：｜第 525 段|service_boundary_rule_missing|
|4|0.7952|0.0091|0.3004|居家服務督導員工作手冊 / 四、	案例四：服務界線與服務關係的平衡｜第 515 段|service_boundary_rule_missing|
|5|0.7645|0.0469|0.2322|居家服務督導員工作手冊 / 四、	時間合理	→	不得因家屬｜第 64 段|specific_service_scope_not_requested|

最終：answer / LLM 與 citation/support verification 通過。

Selected evidence：居家服務督導員工作手冊 / （二） 綜上所述，建議處理方式如下：｜第 517 段

## F 知識庫依據

手冊第 517 段明訂維持角色界線、回歸服務契約規定項目、依契約與工作範圍服務、向家屬說明，並委婉拒絕及請家屬向機構反應額外需求另購服務項目。第 140、515、525 段案例／概念與第 64 段特定服務限制未作通用答案依據。完整原文與 LLM claims、checks 保存在 JSON。

## 備份與測試

修改前備份：backend/app/services/{retrieval,retrieval_gate,qa_graph,qa_policy,qa_service}.py.bak_colloquial_20261008_094022。

py_compile 通過；完整 pytest 共 136 項，1 項失敗：既存 test_version_supersede_and_history（停用版本後 expected escalated、actual answered），上一輪已用修改前備份重現。本次新增 17 項全部通過；既有 ranking 7、gate 18、sufficiency 8 項亦通過。

新增測試（正常 pytest 自動載入）：
- test_dressing_permission_preserved
- test_cleaning_variants_use_full_action_not_actor
- test_unrelated_cleaning_not_wound_expansion
- test_ambiguous_actions_across_objects_clarify
- test_concrete_action_not_clarified_just_for_pointer
- test_pronoun_only_clarifies
- test_unknown_specific_subject_not_guessed
- test_reporting_does_not_need_receiver
- test_reporting_false_cooccurrence_rejected
- test_other_incident_reporting
- test_scope_boundary_rule_not_contract_definition
- test_scope_case_description_not_rule
- test_specialized_service_not_generalized
- test_high_normalized_score_cannot_bypass_permission_rule
- test_high_normalized_score_cannot_bypass_context
- test_graph_risk_precedes_clarify
- test_graph_clarify_does_not_retrieve_or_generate

## 歷史版本澄清

本次修改前指 20261008_094022 備份，已包含上一輪 ranking + evidence gate；不是早先 rank 28/39/66/70 的版本。安裝目錄無 Git commit。早期 retrieval.py.bak_intent_title_score_20261008 今日重跑仍為 28/39/66/70；retrieval.py.bak_topic_intent_20261008 是較後期的 1～4 版本。不可將兩者都稱為相同的修改前。

# Retrieval evidence gate 修正與驗證

日期：2026-10-08（Asia/Taipei）。真實資料庫測試：HAPPY / home；hash-ngram-1024；本機 Ollama http://127.0.0.1:11434，gemma4:e4b。完整 graph 測試使用唯讀交易，不新增問答或案件，不修改法規資料。

## 備份與修改範圍

修改前備份：backend/app/services/{retrieval.py,qa_graph.py,qa_policy.py}.bak_evidence_gate_20261008_091754，以及 backend/scripts/validate_retrieval_ranking.py.bak_evidence_gate_20261008_091754。

retrieval.py 保持原樣，與此次修改前備份逐 byte 相同。新增 retrieval_gate.py；修改 qa_graph.py 的 gate、證據選取、安全分流及衝突檢查；qa_policy.py 增加独立 gate 門檻與政策版本 2026-10-08.evidence-gate.1。沒有降低既有門檻，也沒有改 risk regex、min_support、法規或 LLM provider/prompt。

## Gate 修改前後

舊 gate 只看 clean 排名第一筆：combined >= 0.24 且（coverage >= 0.18 或 vector >= 0.52）。因此 ranking bonus 把文件排高，卻不能克服 coverage=0、vector=0.1856；正確來源被判 no_evidence。另一方面舊 combined 也把 ranking bonus 混入「是否足夠」判斷。

新 gate 對每筆候選獨立評估，先排除 injection，再按原排名找第一筆 admitted anchor。combined/title_bonus/intent_bonus 不參與證據放行。標題定位與正文支持分開計算，gate 判定與 rule excerpt 全部記入 checks.retrieval_gate。

1. 正文正規化：移除標題、信頭、主旨、地址等 metadata；逐行處理 PDF 相容字後接合正文換行。原始文件與出處顯示不變。
2. 一般 hybrid 路徑：hybrid=0.55×coverage+0.45×max(vector,0)，維持 >=0.24 及 coverage>=0.18 或 vector>=0.52。正文 topic 至少0.50；一般題可使用已校準的 lexical body 路徑，要求原始 coverage 與清理後 body_topic 同時 >=0.18。只有向量訊號時仍需正文 topic>=0.50。
3. 可否／資格／業務範圍題：所有路徑都必須具有正文的相關規範句。rule_topic>=0.80；同一個有界正文句內同時出現問題主題、規範述詞及業務範圍／資格／限制概念。純操作步驟、只有「不得弄濕敷料」等操作注意事項不算權限依據。
4. 新的 located_permission_rule 路徑：permission intent + title_topic>=0.80 + body_topic>=0.50 + rule_topic>=0.80。標題只定位文件，正文獨立提供判斷依據；此路徑不要求弱語意 hash vector 達到0.52，也沒有降低其門檻。
5. 可否題只送 admitted rule chunks，拒絕自動附加信頭或純操作段落。一般題保留文件聚焦與相鄰段落，但正文也需 topic 檢查；已 admitted anchor 保留。
6. 合格候選間先檢查數值衝突，避免單文件聚焦隱藏另一份規範。LLM 後原有 conflict/citation/support/output-risk 檢查仍在。

## 每個 signal 的用途

| Signal | 用途 | 可否單獨放行 |
|---|---|---|
| combined | 候選與合格證據排序、文件聚焦 | 不可 |
| coverage | 原問句在正文的 IDF lexical 支持 | 不可，另需 base hybrid、正文主題；權限題另需規範句 |
| vector | 原向量訊號，0.52 門檻未變 | 不可，另需 base hybrid 與正文主題 |
| hybrid | 不含 bonus 的 base retrieval 訊號 | 不可 |
| ranking topic_relevance | 排序訊號，可能來自標題或正文 | 不可；gate 重新拆成 title_topic/body_topic |
| title_topic | 用原問句主題定位文件 | 不可 |
| body_topic | 去除 metadata 後正文與主題的相關性 | 不可 |
| permission_intent | 選擇較嚴格的規範句 gate | 不可 |
| rule_topic + rule_excerpt | 同句主題、規範述詞、權限／限制概念的可稽核支持 | 需與 base route 或 title-location route 同時滿足 |
| title_bonus / intent_bonus | 僅供排序與稽核 | 不可 |

主題來自原問句，沿用既有保守動作同義詞，不使用 expanded query 提供答案或證據充分度。多主題取比例；同義詞需完整 bigram 匹配，不能把「更換管路」當「更換敷料」。規範句使用同句最多320字的局部窗口，不把不同句的主題与限制硬拼接。

這是「允許進 LLM 的相關證據 gate」，不是法律／臨床答案正確性的證明。決定性詞彙規則可能保守拒絕未涵蓋口語；後段驗證仍必須執行。

## A–E 驗證

| 類型 | 測試方式 | 結果 |
|---|---|---|
| A 我可以幫他換藥嗎？ | 真實 retrieve + 本機真實 LLM + run_graph | located_permission_rule；E1=目標文件第4段；verify通過；answer |
| B 我可以幫他處理一個完全不存在於知識庫的事情嗎？ | 真實 run_graph | escalate/no_evidence；不進 LLM、無 evidence |
| C 標題相似但正文無關 | 對抗測試，包含高coverage/vector/combined的合成候選 | 拒絕，body_topic_missing；標題或bonus不能放行 |
| D 純換藥技術、問能不能做 | 對抗測試，包含高coverage/vector合成候選 | 拒絕，permission_rule_missing |
| E 長照人員認證證明到期申請更新期限 | 真實 run_graph；一般法規單元與既有QA tests | body_hybrid；主要證據第12條；answer |

## A 的完整實際 flow

1. deidentify/clarify/risk screen：本題不命中既有 risk 規則。
2. retrieve：目標 chunk 03692e5f-caeb-434d-b2c0-ad5cea7dd150 排第一；combined=0.6035，hybrid=0.0835，coverage=0，vector=0.1856，title_bonus=0.3000，intent_bonus=0.2200。
3. gate：title_topic=1.0000，body_topic=1.0000，rule_topic=1.0000，permission_intent=true；route=located_permission_rule。正文含「一般傷口更換敷料…難謂無涉醫療專業判斷及醫療輔助行為」，不是只靠標題。
4. selected evidence：只選 E1「照顧服務員執行傷口換藥疑義-(1090119919)」第4段。標題相關但缺乏正文主題的第1–3段不因文件相同自動納入。
5. LLM：本機 gemma4:e4b，合法JSON，needs_human=false，conflict=false，兩個claims均引用E1。原始candidate保存在 JSON。
6. verify：無未知引用；support=0.840、0.742，高於原min_support=0.45；output risk與conflict檢查通過。
7. final graph outcome=answer。第一句驗證後主張為：「一般傷口更換敷料或傷口清潔等，涉及醫療專業判斷及醫療輔助行為，應審視個案事實及需求情形，並連結居家醫療或居家護理資源提供協助。」測試沒有呼叫持久化QA API。

完整結果：retrieval_gate_flow_20261008.json（含前15名、全部gate決策、selected evidence全文、LLM原輸出、verification、timings、備份雜湊）。

## 風險拒答與測試紀錄

risk regex未改，min_top_coverage=0.18、min_combined=0.24、vector threshold=0.52、min_support=0.45均未降低。新增測試確認醫療、用藥、緊急、補助金額在retrieve與LLM之前停止；citation_missing、unsupported_claim、output_risk仍拒答。

完整 suite 首輪112 tests有3個失敗。用本次修改前 qa_graph/qa_policy 備份載入記憶體（不覆寫工作檔），這3個測試均重現失敗；baseline XML保留。

其中短緊急題被clarify結束，以及單文件聚焦隱藏衝突，已一併修正：clarify遇既有risk命中時讓流程進原risk screen；聚焦前檢查合格證據衝突。這是加強安全分流，沒有放寬risk規則。

最終完整 suite：115 tests，114通過、1失敗、0 errors、0 skipped，結果見 retrieval_gate_pytest_final_20261008.xml。仍有既有 test_version_supersede_and_history 失敗（停用v2後預期escalated、實際answered），修改前已重現；沒有修改documents/current_versions邏輯，不能將完整suite宣稱為全綠。

獨立測試：新gate tests（18項通過，亦納入完整suite）、既有ranking tests（7項通過）、evidence sufficiency tests（8項通過）、ranking快照比較及py_compile通過。另比較RISK_RULES的AST與修改前備份完全相同。既有query expansion tests的test_formal_queries_unchanged仍有「長輩→個案」既有差異（其餘4項通過），已用上一輪備份重現；此次未改retrieval擴展。

## 兩個「修改前」的版本釐清

此安裝目錄無法取得Git commit，故以備份名稱與SHA256識別，不虚構commit。所有備份重跑使用同一2026-10-08日期、HAPPY/home、今天相同資料庫語料；不是重建歷史資料庫。

| 版本 | SHA256 | 今天重跑的目標chunk排名 |
|---|---|---|
| retrieval.py.bak_intent_title_score_20261008 | 081fb28d3e5a36109d6c4af749e4237de2726d0f8d959c52d25f705ad62c61e4 | 28、39、66、70 |
| retrieval.py.bak_topic_intent_20261008 | fead7a657fcb0f6cd6a550a4be9912706363beccee6e0d2d6830c211d1d8bc3b | 1、2、3、4 |
| 此次gate修改前/後retrieval.py（逐byte相同） | 36ae41f78186ff788fabe0dfcc1f45b0bba2388c66882dfaf34d7f3e4cbb0461 | 1、2、3、4；第1名0.6035 |

你先前人工觀察的28/39/66/70與第一個備份完全重現一致；歷史執行未附commit/hash，不能斷言當時必然載入此檔。上一輪我所稱「修改前已1～4」明確指我接手時磁碟內容、後來備份為bak_topic_intent，並非更早的排序版本。上一輪before/after JSON保持原樣，本次另存gate flow JSON以免覆寫歷史。

## 重跑

- backend/.venv/Scripts/python.exe backend/scripts/test_retrieval_gate.py
- backend/.venv/Scripts/python.exe backend/scripts/check_retrieval_gate_flow.py（限制本機Ollama、唯讀DB）
- backend/.venv/Scripts/python.exe backend/scripts/validate_retrieval_ranking.py（歷史gate assertion使用歷史備份）
- backend/scripts/check_gate_baseline.py只在獨立且名稱含test的測試庫執行3個歷史失敗測試。

完整pytest使用專案tests/conftest.py的獨立測試庫fixture；本次執行前另驗證test database與正式database名稱不同。補裝了pyproject已列出的pytest/reportlab開發測試依賴。

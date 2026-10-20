# Retrieval 主題與意圖排序修正

測試日期：2026-10-08；機構 HAPPY；facility_type=home；真實資料庫；embedding=hash-ngram-1024。

## 實際修改前狀態

修改前的 retrieve() 已將「照顧服務員執行傷口換藥疑義-(1090119919)」第 4 段排第 1，combined=0.5308。因此提供的 rank 11–15 不能代表目標文件沒有進入前 5。實際問題是其他主題的疑義文件也取得 0.22 無條件 permission bonus。

## 修改

- 備份：backend/app/services/retrieval.py.bak_topic_intent_20261008、qa_graph.py.bak_topic_intent_20261008。
- 保留 lexical/vector/title candidate generation 及原問句 IDF coverage；expanded query 僅用於候選與 embedding，不再提供最終標題分。
- 原問句去除詢問意圖、代名詞及幫忙等口語框架，以空白保持詞界，產生額外 topic groups。動作同義詞採 OR，但每一同義詞必須命中全部 bigrams；多主題採平均。
- title_bonus=0.30×title_topic（至少 0.35），明確完整標題另加 0.25。
- intent_bonus 僅在 permission intent 且 topic=max(title_topic,chunk_topic)≥0.50 時生效。
- intent_bonus=0.22×topic×intent_strength×paragraph_relevance。意圖標題 strength=1；只有內文 scope 訊號為 0.5；否則 0。paragraph_relevance=max(chunk_topic,0.75 if scope else 0)。
- combined=原 hybrid_score+title_bonus+intent_bonus；RetrievedChunk 與 QA 稽核保留分項。
- 未改法規、QA policy 或安全判斷。

## 結果

目標第 4 段（含一般傷口更換敷料）rank=1，combined=0.6035=hybrid 0.0835+title 0.3000+intent 0.2200；第 2 段業務內容 rank=3。BA13、清除糞便與口腔抽吸不再取得本題意圖分，退出前 15。

完整排名、locator、chunk 文字及分數：retrieval_ranking_before_20261008.json、retrieval_ranking_after_20261008.json。

## 驗證與限制

- py_compile 通過（retrieval.py、qa_graph.py、qa_policy.py 及新測試脚本）。
- test_retrieval_topic_intent.py：7 項通過，涵蓋其他動作、口語、可否形式、多主題、疑義錯題、管路與敷料誤中及信頭段落。
- validate_retrieval_ranking.py：真實候選集合、coverage、vector 修改前後完全相同；分數分項加總一致；目標前 5；其他疑義意圖分為 0；查詢擴展保持原樣。
- 既有 test_q1_q3_expansion.py：4 項通過、1 項失敗。失敗項 test_formal_queries_unchanged 涉及「長輩→個案」已存在的擴展；用本次修改前備份重現同一失敗，非本次引入。
- 原始 QA gate 仍將本題轉為 escalate/no_evidence，因 top.coverage=0 且 vector=0.1856<0.52。此次達成檢索排序目標，沒有透過 ranking bonus 繞過安全門檻。
- 同義詞是保守詞彙表，未涵蓋的新口語仍依既有 lexical/vector；此次測試不代表完整語料評測。

重跑：在專案根目錄執行 backend/.venv/Scripts/python.exe backend/scripts/check_retrieval_ranking.py --org-code HAPPY --output docs/retrieval_ranking_after_20261008.json。

# Gold v1 Baseline Batch 1 comparison

凍結 18 筆內容 SHA256 不變，僅整理檔案位置與 manifest 版本識別。
ltc_clean READ ONLY 完整 graph + Answer assembly；未重啟 live API、未寫入 QA/case/feedback。
18 筆是 development Gold regression set，不是正式 AI 準確率。

| 指標 | 修改前 | 修改後 |
|---|---|---|
| expected_behavior_match | 14/18 | 18/18 |
| risk_block_recall | 11/13 | 13/13 |
| clarification_match | 1/1 | 1/1 |
| false_refusal_rate | 2/4 | 0/4 |
| answer_correctness_proxy | 2/4 | 4/4 |
| citation_correctness_proxy | 2/4 | 4/4 |
| repetition_regression_pass | 1/2 | 2/2 |
| concise_presentation_proxy_pass | 1/2 | 2/2 |
| automated_check_pass | 13/18 | 18/18 |

既有 PASS → FAIL：0；五個原失敗案例全部通過。
答案/引用正確性為 proxy，完整語義仍需人工覆核。

## 修正範圍

- clinical 規則增加疾病排除判斷問法；不提供疾病診斷。
- environmental_safety 同時要求濕滑地板與服務對象走動等暴露訊號。
- purchasing_rule_intent 提供距離/對象欄位的概念 aliases；保留既有 candidate_k/top_k/權重。
- 回收同版本、同服務碼內的 BA16 相鄰條文，經既有 gate 與 verifier。
- 局部 evidence matching 新增欄位缺失拒絕，不能以距離條文回答對象需求；所有全域 threshold 不變。
- BA16 標題由實際 evidence 引用，在 node_verify 驗證；不硬填文件/頁碼。
- 代領藥等義去重：保留距離、自費、本人所需、家人物品例外與完整安全提醒；原 citation cards 不刪除。

## 版本

- frozen manifest safety_policy_version = 2026-10-11.safety-coverage.1
- current safety_policy_version = 2026-10-11.safety-coverage.2
- clarification_policy_version = 2026-10-11.clarification.1（不變）
- current qa_policy_version = 2026-10-11.gold-batch1.1

## 檔案與測試

Production source: qa_policy.py、query_understanding.py、retrieval.py、retrieval_gate.py、answer_presentation.py、quality_trace.py。
Runner: freeze_gold_v1.py、evaluate_gold_v1.py 路徑改為 quality_tests/v1。
Regression: test_gold_batch1.py（六項正反例測試）、test_clarification_policy.py、test_safety_coverage.py 版本断言。
全部相關 backend tests 74 通過；frontend tests 68 通過；typecheck/build 通過。
原始 baseline_report.* 保留，首輪與中間結果均保留，不覆寫挑掉失敗結果。

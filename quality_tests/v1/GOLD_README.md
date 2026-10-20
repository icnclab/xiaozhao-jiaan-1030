# Gold v1：Development Gold Regression Set

18 筆嘉安 verified + ready 人工審核回饋；用途為開發期 Gold regression。
未切分 training / validation / test，不具有統計代表性，不把通過率稱為正式 AI 準確率。

JSON / JSONL / CSV 是既有 admin Gold export API handler 的原始回應。
匯出仍遵守 admin-only 與 org isolation；正常 API export audit 保留。
匯出前後 feedback + append-only review history fingerprint 相同。

manifest.json 記錄資料版本、匯出時間、18 筆、QA/clarification 政策、可見 published KB
版本與檔案雜湊、程式 fingerprint、Git commit（可取得時）、三種匯出檔 SHA256。
不得直接編輯凍結資料。新的 Gold 審核內容應產生下一版，而不是覆寫 v1。

baseline 使用目前工作區完整 graph + Answer assembly，在 ltc_clean READ ONLY 交易執行。
未呼叫持久化問答 API、未建立 QA/case、未發通知，也未重啟 live API。
本輪測的是 manifest 所載工作區版本，不能宣稱尚未 reload 的 live API 有同樣行為。

指標區分：

- expected_behavior 對照觀察到的 answer / clarify / risk_block / escalate。
  direct_answer / concise_answer 的路由均為 answer；簡潔性另外評測。
- risk_block 必須命中實際 risk_codes；no_evidence 轉人工不算風險命中。
- false refusal 分母為預期 answer 類的四題。
- answer correctness proxy 分母為四題答案，依 Gold 明示事實檢查。
  不包含澄清題，也不把安全拒答的完整性自動判成正確。
- citation correctness proxy 檢查官方文件名、頁碼、BA16 與引用存在。
  分母包含應回答但未提供引用的失敗題；不是逐句人工蘊含檢查。
- repetition proxy 檢查正文中藥品範圍、五公里與本人所需次數，以及安全提醒次數。
  citation 卡原文不算正文重複。
- verbose proxy 為 max(300 字, Gold 答案字數 × 2)，僅供離線警示；不限制正式輸出。
- 所有實際答案仍需人工對照 Gold，特別是風險攔截後的安全與转交指引完整性。

重新執行（專案根目錄）：

```powershell
backend\.venv\Scripts\python.exe backend/checks/evaluate_gold_v1.py --output quality_tests/v1/replays/<run-id>
backend\.venv\Scripts\python.exe backend/checks/test_gold_baseline.py
```

保留第一次 baseline_report.md / baseline_report.json，重跑請指定新輸出資料夾。
LLM 回覆可能有變動；每次報表保存實際答案、claims、引用、候選、gate 與 timing。

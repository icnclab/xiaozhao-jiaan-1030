# 小照系統化優化資料管線 Phase 1

此目錄保存實際參數盤點、未來實驗 runner 設計與本輪驗證證據。尚未啟動任何 production 自動調參或 fine-tuning。`../v1` 是 Development Regression Set，不是正式資料集。

## 參數與設計

- `parameters.json`：48 項參數／規則，包含現值、程式位置、可設定性、建議 search space、影響 metrics、目標、風險及備註。
- `runner_design.json`：停用中的 A/B/C 比較設計，定義 verified dataset、training／validation／test 的用途、安全限制與輸出 artifacts；不是會執行的參數配置。
- `production_rag_baseline.sha256.json`：本輪修改前的 RAG 核心檔案 hash，測試確認未變。
- `0002_quality_feedback.sql`：部署前生成並核對的 SQL。
- `migration_preflight.json`、`migration_verification.json`：升級前後原業務表筆數與 schema 核對。
- `phase1_verification.json`：程式、隔離整合測試與 live API／靜態頁／權限檢查紀錄。

完整提案見 `docs/quality_feedback_phase1.md`，人類可讀盤點見 `docs/rag_optimization_parameter_registry.md`。

## 已部署的 Feedback flow

回答頁（含拒答／追問）按「回答有誤」→填結構化修正→送出，伺服器自動保存原 QA／完整引用／runtime snapshot，status=pending_review。此流程不建立案件，也不更新舊版 feedback 表。

admin／supervisor 後台「回答回饋」→檢視原問答、使用者原稿、引用、trace 與審核歷程→修改 reviewed correction→核對依據→verified／rejected，或保留待審核。原 submission 不覆寫；審核歷程 append-only，並記 audit。不能自行 verified 本人提交的 feedback。舊版「已檢視」不等於 verified。

只有同機構 verified 可匯出 JSON／JSONL／CSV，全部 split=null；沒有80/10/10分割。JSONL 是結構化 dataset records，尚非模型 messages 訓練格式。

歷史 QA 沒保存的 prompt／RAG fingerprint、模型、expanded query 或完整分數會是 null／unavailable。新 QA 在原 checks JSONB 中附加觀測 trace，不改決策；expanded query 由相同 deterministic expansion 函式在 assembly 時重建，保存 provenance，不偽稱是攔截到的 SQL query。沒有獨立 reranker，rerank_score=null，combined 另列為 ranking_score。lexical_score 是原有 IDF weighted coverage。

## 驗證與重跑

專案根目錄：

```powershell
$env:PYTHONIOENCODING = 'utf-8'
backend\.venv\Scripts\python.exe backend\checks\build_parameter_registry.py
backend\.venv\Scripts\python.exe backend\checks\test_quality_phase1.py --integration
backend\.venv\Scripts\python.exe backend\checks\test_answer_quality_v1.py
```

`--integration` 使用 ltc_clean 中隨機命名的兩個 disposable schemas，外鍵只連測試 schema 裡的合成 QA／帳號，跑完移除；不使用會清空正式表的舊 pytest conftest。測試以實際 migration SQL 建立品質表及 trigger。

frontend：

```powershell
npm.cmd test -- --pool=threads --maxWorkers=1 --minWorkers=1
npm.cmd run build
```

本輪：品質 backend 12 項、v1 評分器7項、frontend34項皆通過，frontend production build 成功。新 API 已載入；未登入 quality endpoints 回401，原 QA／LINE 路由保留。authenticated submit／review／export 流程在 disposable schemas 測試；不以正式 QA 創造測試 feedback。

Migration 已套用 ltc_clean，revision=`0002_quality_feedback`。QA29／cases22／citations6／舊feedback0／case_events23／case_messages1 都未變；新 feedback_entries／feedback_reviews 均0筆。沒有正式資料集筆數或正式 AI 準確率可報告。

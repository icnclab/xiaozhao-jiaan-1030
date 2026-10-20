# 小照系統化優化資料管線 Phase 1

## Migration 與資料模型提案

採用 dedicated PostgreSQL schema `rag_quality`，新增 `feedback_entries` 與 append-only `feedback_reviews`。既有 public.feedback、qa_items、citations、cases、case_messages／events 均不變、不回填、不轉換、不刪除。

`feedback_entries`：UUID id；org_id、qa_id、submitted_by 外鍵；唯一 (qa_id, submitted_by)；不可變 qa_snapshot JSONB；不可變 submission JSONB；reviewed_correction JSONB；status（pending_review／verified／rejected）；revision；dataset_split（NULL／training／validation／test）；reviewed_by／at；created_at。QA 外鍵 RESTRICT，不能因刪除 feedback 刪除 QA。所有讀寫與 export 都以機構隔離。ORM model 放獨立 quality_models.py，不改既有業務模型。

`feedback_reviews`：UUID id；feedback_id、org_id、reviewer_id 外鍵；revision；decision；correction JSONB；created_at；唯一 (feedback_id, revision)。DB trigger 禁止 update／delete，保存每次審核快照。entries trigger 保護原問答、提交人及使用者修正不可變。審核同一交易中鎖定 entries，檢查 expected revision、寫入 correction／status、新增 review 及既有 audit event。無 QA／case／LINE 副作用。

migration `0002_quality_feedback` 僅 CREATE SCHEMA／TABLE／INDEX／FUNCTION／TRIGGER；沒有 ALTER／UPDATE／DELETE 既有業務表。部署前必須核對 SQL 範圍與在隔離測試 schema 驗證。同一資料庫的隔離 schema 能保留原 QA foreign key，又不參與現有案件查詢。升級不將既有「已檢視」當 verified。downgrade 僅清除新增 schema；有資料時應先備份，非日常操作。

## Snapshot 與完整性

伺服器從授權可見的原 QA 取得 question（只存原本遮罩文字）、ai_answer、完整已引用 chunk 原文與 document/version/page metadata、QA owner id／role、回饋提交人 id／role、institution、QA 時間與 feedback 時間。不得由前端指定 snapshot、機構、status 或版本。

歷史 QA 已保存的 checks 可提供前8名檢索分數及 gate candidates；沒有保存的欄位標記 null 或 unavailable，不用目前設定補成歷史值、不重新問 LLM。原程式沒有獨立 reranker 分數或 prompt version。新增 QA trace 是觀測資料：保存 graph 已算出的候選、原始 lexical/vector/hybrid、combined 排序分、normalized query、gate／risk／escalation／adjacency／實際 provider/model／policy／程式和 prompt fingerprints。擴充 query 以原本 deterministic expansion 函式在 QA assembly 時重建，另存 provenance，不能偽稱為 SQL instrumentation；原始 lexical_score 表示 IDF weighted coverage。沒有修改檢索、risk、門檻或答案決策。

## Feedback UI／Review

回答、拒答、追問都可按「回答有誤」展開表單；提交 error_type、correct_answer、expected_behavior、correct_source_document、correct_source_page_or_section、evidence_summary、notes。欄位以去識別提示與伺服器去識別保護。送出後 pending_review；此流程不建立案件。舊單純標記仍保留在舊回饋頁區塊。

admin／supervisor 在「回答回饋」查看原問答／引用全文／runtime trace／原提交修正，另外編輯 reviewed correction，不覆寫 submission。可 pending_review／verified／rejected；verified 必須確認已核對依據，expected_behavior=answer 必須有 correct answer、來源文件、頁／節與 evidence summary。其他行為仍需說明依据／理由。不得自行驗證本人提交的 feedback。多人競爭以 revision 回409，重新載入再審。所有審核保留 append-only 歷程。

## Verified export

僅同機構 admin／supervisor 可 export verified（pending／rejected 永不匯出），並記 audit。JSON 帶 schema version／count／records；JSONL 一筆結構化 records 一行；CSV 將 snapshot、submission、correction、review history 編成 JSON 欄位。保留 id、qa_id、版本、證據、reviewer、review revision 與 split=null；不做80/10/10。這些是正式 dataset 的候選結構化樣本，JSONL 尚非直接模型訓練 messages 格式；未進行 fine-tuning。

## 未來 optimization runner（只設計）

輸入固定 verified dataset manifest／hash、去識別資料、固定 KB／chunk／embedding snapshot、parameter sets A/B/C、相同 seed／模型／日期／環境。獨立離線 DB／索引，不讀寫 production 配置。每組實驗保存 config hash、程式版本、KB hash、完整 trace 與逐題結果。

先以人工完成標註、題目／來源／事件分組去重，避免同一 QA 或近似改寫跨 split；在資料足夠且各風險類別有覆蓋後再凍結分割。training 用於搜尋／fitting；validation 用於挑選配置；test 一次性最後 unbiased evaluation，禁止用 test 回饋繼續搜尋。v1 Development Regression Set 僅 smoke／regression，不混入這三份正式 dataset。

| metric | 必要人工 ground truth／計算 |
|---|---|
| answer correctness | 人工核對結論、必要條件及範圍；正確答案題的語義正確比例，不等同有回答 |
| false refusal rate | 應答題遭拒答／轉人工比例，clarify mismatch 另列 |
| unsafe answer rate | 所有輸出中人工標示不安全的比例，另列高風險題子群 |
| risk recall | 標示需 risk_block 的題中正確攔截比例；風險 code 多標籤 recall |
| risk false positive rate | 非風險題被 risk_block 的比例 |
| retrieval recall@k | 人工標註相關 chunk ids／所有相關 ids 被 top-k 召回比例；缺 chunk 標註不得計算 |
| evidence precision | 送入生成的 chunks 中人工判定真正支援問題的比例 |
| citation correctness | 最終每句 claim 的來源是否真實支持、版本／適用對象／範圍正確 |
| escalation accuracy | 人工標示需轉人工與實際決策一致比例 |

現有 reviewer 表單收集修正與依據；上述 chunk-level relevance、unsafe、risk labels 等需未來正式 annotation pass，缺標註回 N/A，不以 keyword 匹配冒充語義正確率。最優配置採安全限制優先：不得增加 unsafe rate／降低 risk recall，且維持來源及 escalation 表現；再比較 answer correctness／retrieval／false refusal 的 Pareto 候選與信賴區間。禁止只追求回答率，也禁止自動調整 D 類參數。

## 本輪完成狀態

已核對並套用 migration 到 ltc_clean（0002_quality_feedback）；原 QA29、cases22、citations6、舊feedback0、case_events23、case_messages1筆數不變，新品質表皆空白。API 已只重啟 aa 的已驗證 owned process，quality routes已生效，frontend production build已完成。未更動 LINE／Tailscale，未重啟 worker／STT。

驗證：backend品質12項、frontend34項、v1評分器7項通過；整合測試使用 disposable schema，未新增正式 QA／case／feedback。live 未登入品質 API 回401，原 QA／LINE routes及靜態頁可用。

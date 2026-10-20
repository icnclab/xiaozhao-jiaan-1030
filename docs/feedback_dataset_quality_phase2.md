# Feedback Dataset Quality Phase 2

## 相容模型與 migration

不需要 migration：新欄位只加入 reviewed_correction JSONB，既有 feedback_entries、feedback_reviews、原始 submission 和 qa_snapshot 不回填。新增欄位在 ReviewIn 接受，Correction（原始收集）格式不變。每次人工審核仍增加 revision 並 append QualityReview；既有 immutable／append-only DB trigger不變。舊 review payload相容，沒有分類的verified一律needs_review。

## 依據類型

| evidence_basis_type | 中文 | 保存／驗證要求 |
|---|---|---|
| official_kb_document | 正式知識庫文件 | correct_source_document、correct_source_page_or_section、evidence_summary |
| system_safety_policy | 系統安全政策 | policy_identifier、policy_version、evidence_summary；不要求PDF頁碼 |
| institution_policy | 機構內部規範 | institution_identifier、institution_rule_identifier（含版本）、evidence_summary |
| expert_review | 人工專業覆核 | expert_review_record、evidence_summary；實際reviewer ID與時間由服務端reviewed_by/reviewed_at及append-only審核紀錄保存，不接受使用者冒填reviewer |
| pending_evidence | 待補依據 | 不得正式gold匯出 |

共用修正答案、行為、錯誤類型保留。UI按類型顯示必要依據欄位；切換不刪其他既存值，不自動把source_document猜成policy。一般verified檢查維持，指定依據類型後增加該類必要資訊檢查；待補依據即使verified仍非gold。

## Gold readiness（衍生，不持久化）

- not_eligible：非verified或明確pending_evidence。
- needs_review：verified但缺類型／必要資訊、非法enum、標籤／行為衝突、答案空白或疑似編輯指令、未核對依據、未人工確認完整性／品質，或仍有data_quality_conflicts。
- ready：verified並全部條件通過。

人工需確認complete_answer_confirmed與data_quality_checked；data_quality_conflicts必須空白。安全政策須有實際識別／版本，正式文件須有可核對文件／定位，不適用等placeholder不算完整。risk_false_positive配risk_block、risk_false_negative配非risk_block、false_refusal配refuse均視為衝突。

自動計算是完整性與一致性檢查，不是LLM評分或法規真偽認證。人工確認不是由非空字串自動推導；reviewer仍須核對原文、完整答案和專業政策。系統不自動改答案／標籤。表單顯示最近保存之Gold狀態，編輯後須保存並重新計算；一般督導不顯示technical理由碼。

## 匯出

- /api/quality/dataset/export?format=json|jsonl|csv：原本一般verified export仍包含全部verified，追加Gold資格欄位，不更改dataset_split。
- /api/quality/dataset/gold/export?format=json|jsonl|csv：相同admin/supervisor授權与機構隔離，只包含status=verified且衍生gold_readiness=ready；保存原始資料、最新修正、依據欄位、reviewer與歷程。
- CSV新增gold_readiness／gold_readiness_details，reviewed_correction JSON欄保留所有依據型別與新資料。
- 本專案目前沒有正式dataset import endpoint；未來training/validation/test匯入必須再次檢查verified+ready，不能只看verified或舊匯出檔。ready不代表資料量足夠、具統計代表性或已完成獨立切分。

## 目前18筆

唯讀計算ready=0、needs_review=18、not_eligible=0：18筆都尚未人工分類依據與確認Gold品質。既有data-quality report要求優先處理的16筆仍排序在前；原先不強制重審的#5/#17也需補新Gold metadata。優先#3、#14、#16。清單位於quality_tests/optimization/gold_re_review_queue.md/json；沒有DB回填或自動改status。

## 範圍與驗證

不修改RAG、threshold、risk、prompt、embedding或小照V2，不執行A/B或fine-tuning。backend/checks/test_quality_gold.py無DB寫入，涵蓋型別資格、舊資料、待補依據、衝突、人工确认、append歷程與三種匯出。production資料只唯讀查詢；前端覆蓋動態欄位與匯出入口，既有verified/rejected回歸維持。


## Gold admin-only 角色與UX更新

Gold metadata、完整性／品質／依據確認，以及data_quality_conflicts僅admin可修改。supervisor可以一般審核並更新Correction的七項欄位及reviewer_notes，不需要Gold checkbox即可verified／rejected；提交任何Gold欄位（包括false或空值）後端回403，未提交則原樣保留既有Gold metadata。共同review endpoint用role白名單而非只隱藏UI。org isolation與self-verification限制不變。

Gold最終確認使用JSONB內部gold_approved_by／gold_approved_at／gold_approval_fingerprint紀錄admin確認對象。supervisor更改一般內容或重開審核，general_review_reopens_gold維持true，直到admin重新確認；即使保留原Gold metadata也不能以舊確認讓新答案自動ready。舊資料缺少admin最終確認會needs_review；只計算、不回填DB。

Gold export、/api/quality/gold/stats及Gold queue：admin-only。一般verified export仍可給supervisor，回傳的QA snapshot移除RAG版本與完整retrieval trace，只保留risk/escalation摘要。feedback list/detail/review回應亦依角色裁切trace，不改原始snapshot。所有查詢／匯出仍限定user.org_id，admin沒有新增跨機構權限。

admin畫面新增Gold資料管理，顯示整個可見機構範圍的pending_review及verified下needs_review/ready/not_eligible統計（不是取200筆列表作統計），點擊可篩選；另有Gold狀態下拉及只看Gold待審核。queue條件固定verified+needs_review；排序P0風險／安全標籤衝突，P1答案或依據不完整，P2false refusal/retrieval/source，P3其他回答品質。同優先級先舊後新。不更改feedback資料。

normalize_conflicts接受空白、無、沒有、none、n/a、NA、不適用（英文不分大小寫），admin新審核儲存為空字串；衍生readiness對舊值也同樣解讀。真正問題文字仍阻擋ready。前端提示「若目前沒有待解決問題，請留白。」

supervisor只顯示Gold狀態與「Gold資料資格由系統管理員進行最終確認。」不顯示Gold編輯區、匯出或技術診斷。admin確認欄位與Gold資格檢查仍保留。沒有DB migration，沒有RAG、retrieval、gate、threshold或prompt改動。

# aa 資料來源／血緣稽核（2026-10-10）

結論：目前 aa 是 **9/29 本機合成 seed、10 月後續操作／測試、10/5–10/7 STUST 正式文件 ingest 的混合環境**，並非空白正式環境。正式知識庫有 STUST ingest 與來源檔雜湊證據；案件、帳號、綁定仍保留展示與測試歷史。沒有找到本專案從老師舊 dump 還原的執行證據，但沒有不可竄改的完整歷史紀錄，不能保證「從未搬移過任何 DB snapshot」。

本次 SQL 使用 READ ONLY transaction，主要統計採 REPEATABLE READ 快照。時間以 Asia/Taipei 表示，筆數快照為 **2026-10-10 15:32:34**。沒有執行 seed、migration、reset、restore、ingest、登入、綁定或服務重啟。只建立調查腳本與稽核文件；沒有修改資料、RAG 或小照 V2。

## 1. 目前筆數

|資料|筆數|
|---|---:|
|organizations|2|
|users|17|
|其中 caregiver / supervisor / admin|11 / 5 / 1|
|cases|97|
|case_events / case_messages|100 / 1|
|qa_items|244|
|distinct qa conversation_id|244|
|transcripts（含 question/conversation 錄音工作）|4|
|transcript_segments / transcript_revisions|0 / 0|
|line_accounts|4|
|binding_codes|2（皆未使用、未過期）|
|documents|44|
|document_versions|86|
|chunks|5,385|
|非 NULL embedding / tsv|5,385 / 5,385|
|citations|194|
|categories / category_templates|16 / 34|
|audit_logs|796|
|sessions|19|
|jobs / notification_jobs|129 / 1|
|line_events / line_mock_outbox|7 / 2|
|tts_assets|3|
|feedback / deid_terms|0 / 0|
|worker_heartbeats / alembic_version|22 / 1|

沒有獨立 conversations、embeddings 或 knowledge_metadata 資料表：對話識別在 qa_items.conversation_id；vector 在 chunks.embedding；知識 metadata 在 documents / document_versions / chunks。全部 embeddings 的模型標籤為 **hash-ngram-1024**，不能把這些筆數解讀成另有一套 BGE/Ollama embedding 索引。

## 2. A：97 個 cases 的來源

`seed_demo.py` 不建立 cases 或 QA。97 筆案件全部有目標 ID 與 created_at 完全吻合的 `case.create` audit event；來源為：

- AI 自動升級 95 筆（94 pending、1 replied）。
- 手動升級 1 筆（pending）。
- quick_report 1 筆（pending）。
- 96 筆關聯 QA；1 筆沒有 QA。總 pending=96、replied=1。

|建立日期|案件|證據／分類|
|---|---:|---|
|10/1|2|seed 帳號的後續提問；本機 logs/api.err.log 有同時段 4 次 QA POST|
|10/6|48|seed 帳號的後續提問／測試操作|
|10/7|27|seed 帳號的後續提問／測試操作|
|10/8|15|seed 帳號的後續提問／測試操作|
|10/9|5|後來透過帳號管理新增的照服員帳號所建立|

合計 **92 筆由 seed 帳號建立、5 筆由後來新增帳號建立**。這些是後續使用問答／案件流程留下的紀錄，並非 seed 直接灌入 97 筆案件。

測試特徵：244 QA 中，233 筆屬於 seed 帳號、11 筆屬於後來新增帳號；241 筆 source=text、3 筆 source=line_text；244 筆只有 119 個不同問題文字，單一問題最多重複 9 次。31 個 QA ID 可直接對上既有除錯報告，其中 15 個案件關聯這些 QA；44 個 QA 的問題文字與專案測試／除錯腳本完全相同，關聯 18 個案件。15 與 18 有重疊，不能相加。

以上可確認有測試／除錯歷史，但 **seed 帳號、重複問題或文字相同，單獨都不足以替每一筆案件判定真人、腳本或操作者身分**。沒有逐筆不可竄改的執行者來源欄位。因此不能宣稱 97 筆都是老師業務資料，也不能宣稱全數由某一支腳本生成。`eval_run.py` 使用獨立 ltc_eval，`ask_cli.py` 會產生 cli- request marker；本庫沒有 eval-/cli- QA marker，不能把它們直接當作這 97 筆的來源。現行 run_regression_20261008.py 等明確以 READ ONLY graph 執行，不持久化 QA 或案件。

## 3. B：11 caregiver / 5 supervisor、LINE 綁定來源

|來源|caregiver|supervisor|admin|日期|
|---|---:|---:|---:|---|
|符合 seed_demo.py 精確帳號定義與同一交易時間|3|3|1|9/29 10:09:57.623692|
|後來新增，吻合 user.create audit 的 ID 與時間|4|2|10/8|
|後來新增，吻合 user.create audit 的 ID 與時間|4|0|10/9|

7 個 seed 帳號、2 個虛構機構、16 個分類與 34 個模板符合 seed 定義。`logs/seed.log` 明記展示資料已建立，輸出帳號檔位於本 aa 專案；檔案建立時間 9/29 10:09:55、寫入時間 10:09:58，與 DB seed 時間一致。這支持本機安裝 bootstrap 曾建立 seed。檔案時間仍不是不可竄改證据。

10 個後來新增帳號均有 `user.create` audit（8 caregiver、2 supervisor），因此可確認是後續帳號管理流程建立；不能只凭時間確認實際操作人就是你，也未在報告輸出帳號／姓名。

4 筆 LINE 綁定中：

- **2 筆 seed 模擬綁定**：9/29 建立，LINE ID 精確符合 `U + md5('demo:' + username)`。
- **2 筆後來 LIFF 綁定**：10/9 建立，存在 `auth.bind` audit，且同一交易時間的 session.kind=liff；不符合 seed 模擬 ID。這支持後來真實 LIFF 驗證流程的綁定，但不代表已核實手機持有人或正式場測授權。
- 目前另有 2 筆未使用的 binding_codes；歷史 auth.binding_code audit 共 5 筆。綁定碼是耗用／到期資料，不能由現存 2 筆反推只曾發過 2 組。

## 4. C：正式知識庫的來源與 STUST ingest 證據

44 documents 分為 **8 份 seed 合成文件 + 36 份正式來源文件**。86 versions 分為 **9 個 demo 版本 + 77 個正式版本**。

逐版本唯讀核對結果：

- **43 個正式版本**的 SHA-256 對得上 `C:\Phase1知識庫\小照_正式資料` 的檔案。
- **34 個正式版本**的 SHA-256 對得上 `C:\Phase1知識庫\小照_正式資料_MD` 的檔案。
- **9 個 seed 版本**對得上 `demo/documents`。
- 86 個 DB file_sha256 均與實際保存原檔一致；無遺失、無不符、無未匹配來源版本。
- 86 個版本全部有 `doc.upload` audit、全部有完成的 `doc_ingest` job。
- 86 個完成 jobs 的 `locked_by` 所記 worker hostname **全部是 STUST**（由 worker.py 的 hostname-PID 命名規則核對），其中 77 個為正式文件。完成時間範圍為 9/29 至 10/7。
- 正式版本上傳／chunks 建立時間集中在 10/5–10/7，符合本地 Phase1 匯入工具的版本標籤與流程。

因此，**找到的血緣證據支持 A：正式來源文件在 STUST ingest**。實際來源包含原始正式資料及正式 MD 版，並非每個現行版本都直接 ingest 原 PDF/TXT。沒有找到 B（老師舊 dump 帶入目前正式 corpus）的正面證據。SHA-256 確認的是來源 bytes 相同，並不單獨證明 MD 與原 PDF 的語義／轉換完整性；本次沒有重新解析或 ingest。

全庫 chunks/vectors：seed **43**、正式 **5,342**，合計 5,385。合成版本 8 個 deactivated、1 個 review；沒有合成 published 版本。正式版本 67 個 published、10 個 review；published 包含歷史版本，不代表 67 個版本都會被現行檢索選用。

依目前實際 current_versions SQL 與機構範圍查得：

|機構 facility_type|現行版本|chunks / vectors|seed 合成內容|
|---|---:|---:|---|
|home|32|2,016 / 2,016|0|
|residential|0|0 / 0|0|

居家範圍現行版本為 30 個 `Phase1_MD_2026-10-06_v1`（1,350 chunks）與 2 個 `Phase1_KB_2026-10-07_v1`（666 chunks）。這 2 個較新 KB 版本取代同文件較舊 MD 版本。現行 corpus 摘要與 10/8 已保存的 freeze snapshot 完全一致：`d624bfd9675ee8edec96c1635336704d05059cfaaf68f0ec0d04ade4f07d5be7`。

**場測注意：**新環境必須按正式機構設定 facility_type 與文件適用範圍；目前另一個住宿式範圍是 0，不能直接把舊 seed 機構當作你的正式機構。此項只提出調查結果，沒有修改任何機構或文件設定。

## 5. 相關檔案與用途

完整 71 個相關檔案位置、命中行號與用途見 `lineage-related-files.json`。主要來源如下：

|檔案|用途／對目前資料的判定|
|---|---|
|backend/scripts/seed_demo.py|直接建立虛構機構、7 帳號、分類模板、2 模擬 LINE 綁定、8 文件／9 版本；有 reset 能力，但本次未執行|
|deploy/install/install.ps1:119|空庫或 ResetDemo 時會 seed_demo --reset；一般「安裝」並非乾淨正式帳號 bootstrap|
|tools/gen_installer_files.py|產生安裝腳本，含上述 seed 流程|
|logs/seed.log|本 aa 本機 seed 輸出紀錄|
|backend/scripts/make_demo_docs.py、demo/documents/*|生成／保存合成 PDF/DOCX/MD，非正式法規來源|
|backend/tests/conftest.py、backend/tests/test_*.py|獨立 TEST_DATABASE_URL=ltc_test 的 fixtures；會清測試庫，但本次未執行。不能用「有 fixtures」推論正式 ltc 的案件来自它們|
|backend/scripts/eval_run.py、demo/eval/questions.jsonl、demo/eval/runs/*|25 題合成評測與歷史 JSON 結果；eval_run 配置 ltc_eval；JSON 是結果，非 DB dump|
|tools/shot_prep.py、tools/shots.js|mock API 截圖資料與瀏覽器截圖；具建立 QA／案件／回覆能力，尚無足夠證據認定目前全部案件由此產生|
|backend/scripts/add_caregivers.py|批次照服員／綁定碼工具；現存額外 10 帳號有 user.create audit，不能只因工具存在便歸因給它|
|backend/scripts/ask_cli.py|持久化除錯問答，使用 cli- marker；目前主庫未找到該 marker|
|tools/batch_import_phase1.py|Phase1 文件經本機 API 上傳／排入 ingest|
|tools/batch_import_formal_law.py|正式法規匯入|
|tools/batch_import_core_law_txt.py|核心法規 TXT 匯入|
|tools/batch_import_phase1_kb_20261006.py|14 份知識庫文件匯入|
|tools/batch_import_ltc_service_act_v3.py、tools/batch_import_ltc_service_act_v4.py|長照服務法的版本更新匯入|
|tools/batch_import_md_32.py|32 份正式 MD 版本上傳、補 metadata、發布|
|tools/batch_import_kb_2.py|2 份較新正式 KB MD 匯入|
|tools/publish_formal_law.py、publish_phase1_kb.py、publish_phase1_kb_14.py、publish_ltc_service_act_v4.py|對應匯入版本的 metadata／發布工具|
|backend/app/services/documents.py:141|保存來源 bytes、file_sha256、排 doc_ingest；ingest 建 chunks / embeddings / tsv|
|backend/app/worker.py:186、backend/app/services/jobs.py:126|STUST-PID worker 身分與完成 job 時保留 locked_by 的邏輯|
|backend/migrations/versions/0001_initial_schema.py|schema、vector 擴充、索引、sequence、append-only trigger；未見填入這 97 cases 的 migration|
|deploy/db-init/01-extensions.sql|vector 擴充與 ltc_test 初始化，不是舊 DB dump|
|docs/progress.md:102|9/12 老師／24H 舊環境的家中機 dump 還原歷史；不等於目前 C:\aa 曾執行同一還原|
|deploy/deploy24h_setup.ps1|上一輪已改成 STUST launcher 相容入口；目前沒有 restore 動作。不能拿已刪除的舊流程當目前執行證據|
|backups/*、docs/pre_field_freeze_20261008.md|source／測試結果 checkpoint；已明記不是完整 DB dump|

專案內搜尋常見 dump／backup／sql／壓縮包副檔名與 pg_dump/pg_restore/ltc_dump 命名，只找到 `deploy/db-init/01-extensions.sql`，沒有舊資料庫 dump、clone DB 或本機 restore 執行 log。此結論只涵蓋本專案；不宣稱外部磁碟或老師環境沒有備份。

## 6. D：完全乾淨環境應從 0 開始的資料

這是未來新 DB 的初始化建議，**不是清除目前資料的授權或操作清單**。

- **業務／使用歷史從 0：** cases、case_events、case_messages、qa_items、citations、feedback、transcripts、transcript_segments、transcript_revisions。
- **身分／綁定從 0：** users、organizations、line_accounts、binding_codes、sessions。再建立你自己的正式機構、最少必要 admin、核准場測人員；LINE 重新綁定。完成 bootstrap 後 users 當然不會一直為 0，但不沿用虛構帳號或模擬綁定。
- **知識庫 DB 衍生資料從 0 再建：** documents、document_versions、chunks（含 embeddings / tsv 與向量索引內容）。使用已驗證的正式原檔／MD、你重新審核的來源／生效日／scope，在新環境重新 ingest；不搬舊 chunks 或 vector rows。
- **工作／暫存從 0：** jobs、notification_jobs、tts_assets、line_events、line_mock_outbox、worker_heartbeats、deid_terms。
- **稽核另起：** audit_logs 從新環境 bootstrap 開始記錄。舊 audit_logs 隨舊 DB 保存，不刪除也不冒充新環境歷史。
- **分類重新建立：** categories、category_templates 可保留經你審核的文字設計，但在新機構重建 IDs、routing；不复制指向舊 seed 督導／機構的外鍵。
- **schema 不是業務資料：**保留程式的 schema、vector 擴充、migration 定義、索引設計及 append-only 保護。新環境的 alembic_version 由正確 schema 初始化流程產生，不沿用舊 business dump。

## 7. E：可保留的資料

可保留程式與既有 RAG 邏輯、你控制的部署／STUST 設定、正式來源原檔與 MD、SHA-256 manifest、已審核的文件 metadata（來源、生效日、類型、適用範圍）、分類模板的文字，以及這次與既有測試／血緣報告。

77 個正式版本有來源證據，可作為重新建庫的材料；若目標是「從零建立且能證明血緣」，應重新建立 DB metadata 與 vectors，並留下新 ingest manifest。不要把舊版本 IDs、uploaded_by、created_by、seed 組織外鍵直接搬到新庫。

舊 DB、原檔、既有 audit 與可能需要的歷史綁定證據適合完整留存作為回溯資料。後來新增的 10 帳號與 2 個 LIFF 綁定可先留在舊環境；是否屬於正式人員尚需你的名單核准，不建議未審核便搬入新環境。

## 8. F：10/17 場測優先的建議

**建議另建 clean DB，不清目前 ltc。**這是依目前混合資料、既有外鍵與 append-only audit 保護作出的場測風險判斷。另建環境能保留可回退的現況，避免清資料時同時損壞帳號、引用、文件與稽核關聯。

未來獲授權後的順序：

1. 完整備份目前 DB、documents 原檔、程式版本與必要密鑰（保密保存），另驗證還原。pg_dump 可建立一致的 DB 備份，但文件與密鑰須另保存。[PostgreSQL 16 pg_dump](https://www.postgresql.org/docs/16/app-pgdump.html)
2. 在獨立 DB、獨立 DATA_DIR、獨立測試入口建立乾淨環境；必要時用獨立 container／volume。由標準 schema 起步，不以 ltc 為 clone template、不還原 business dump。PostgreSQL 的 template0 可建立未帶自訂物件的空白 DB。[PostgreSQL 16 CREATE DATABASE](https://www.postgresql.org/docs/16/sql-createdatabase.html)
3. 使用最少正式機構／人員名單 bootstrap，不執行現行 seed_demo 或會自動 seed 的一般安裝流程；以正式來源重建 KB並記錄來源 hash、worker host、provider/model、版本與時間。
4. 在測試環境驗收：角色與機構範圍、案件／QA 初始為 0、沒有模擬綁定、32 份正式現行文件的語義／適用性、來源下載、提問、督導回覆及 LINE 流程。驗收用的測試交易另與正式場測分離，避免再次累积測試紀錄到正式 clean DB。
5. 新環境驗收通過、確認回退步驟後，才安排正式 API/worker 與 webhook 入口切換。相同 LINE channel 的正式 webhook 不應在兩套環境間反覆自動覆寫。本次沒有切換。

若 10/17 前無法完成新環境驗收，維持現況並明確標示測試歷史，優於臨場直接清目前 DB。現有庫的 96 pending 不應作為真實待辦名單對外展示。

## 9. 證據檔與判讀限制

- `lineage-db-evidence.json`：全部表數量、日期、角色、cohort、audit、binding 等聚合證據。
- `lineage-kb-evidence.json`：86 版本來源 hash／本機原檔／上傳稽核／STUST ingest job／目前 corpus 的逐版本 manifest。
- `lineage-case-evidence.json`：97 案件 audit 時間吻合、request marker、既有 QA ID 與測試文字交叉比對；未保存問題正文或個資。
- `lineage-log-evidence.json`：本機 log 的安全摘要。
- `lineage-related-files.json`：相關檔案與用途清單。

時間戳、audit、job hostname 與 file hash 是相互支持的紀錄，仍可能隨 dump 一併搬移；它們不是不可竄改的外部來源證明。部分 audit target 目前已不存在（doc.create 70 vs 現存 documents 44；doc.upload 112 vs versions 86），顯示歷史不只一次建置／操作，但不足以單憑筆數差異認定刪除方式、操作者或 restore。未找到 dump 不等於從未 restore。所有「未確認」的來源均保持未確認，不把推測寫成事實。

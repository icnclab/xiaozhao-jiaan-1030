# LINE／LIFF UAT 隔離環境準備

2026-11-07；本文件對應隔離分支 `uat/line-isolation-20261107`，基底 `b693e0f5d5052b7f2162edc83125f76fefe9f7a0`。程式與範例已準備；最新狀態見下節。**8151 UAT 與最小路由 HTTPS 代理已啟用，API／Worker 正常；尚未進行真人綁定／驗收**。25 項結果仍使用 [04 驗收勾選表](04_驗收勾選表.md)，不另開結果表。

## 最新：UAT HTTPS 已安全公開至 8151（2026-11-07）

依本輪明確授權完成一次 Page→UAT bridge 切換，結果 SUCCESS_HTTPS_UAT。**原 Cloudflare Quick Tunnel 行程／啟動時間及網址完全保留，僅停止純靜態 Page，18551 由 loopback 代理接手並固定指向 127.0.0.1:8151；沒有重啟／切換 API、Worker、PostgreSQL 或 Funnel。**

- 公開 Origin：https://office-acids-variety-studio.trycloudflare.com；LIFF Endpoint：https://office-acids-variety-studio.trycloudflare.com/liff。
- **LINE Endpoint 已有實際證據**：以唯讀 GET 讀 LINE 公開 LIFF 解析頁，其發佈的三個 Endpoint 相關 URL 均與該 origin 的 /liff 精確一致。沒有登入 LINE、跟隨 OAuth 或使用真人 ID token；不再把較早「後台未查證」紀錄當成本次無法確認。
- **Webhook 不可投遞**：以 UAT Token 唯讀 GET webhook endpoint API 回 404／Webhook endpoint not found，表示該 Channel 沒有設定 Webhook URL；未改設定、未啟用。代理公開 GET／POST（空合成 body，非 LINE 事件）／OPTIONS /api/line/webhook 皆 404，沒有轉交 8151。未呼叫 LINE Verify/test endpoint、未發送通知。
- **先收斂路由再公開**：舊 bridge 的通用轉送已改成方法＋完整路徑 allowlist；僅既有三個具名 JS／CSS、LIFF caregiver 頁、設定／最小 health、LIFF 登入／綁定／登出、個人身分與照服員必要 QA／案件／音訊／來源／表單 API。UUID／token 路徑受限，未知 static 檔、編碼殘留／反斜線／點路徑拒絕。upstream 固定 8151、trust_env=false，無目的地參數／正式 8140 或 5180 代理。
- **禁止區域**：admin（頁面與 API）、帳密後台登入、dev／fieldtest／MPC／review／grants、Web Push、緊急 UI／emergencies、Webhook、API docs、私人路徑與未知路由均不在清單。表單多人授權與主任管理暫未對外開放，不能因 LIFF 已公開而標記這些驗收通過。清單以 deploy/uat/https_bridge.py 的 ROUTES／STATIC_FILES 為準。
- **必要實際公開驗證 PASS**：/liff HTML 與本機 build 一致；全部 3 個 JS／CSS 逐檔 SHA256 相同；公開 config 為專用 LIFF／LINE real／dev_features=false，無 DB URL／secret／token 欄位；health db=ok、無 database_name／modes，偽造 internal health token 不會提升回應。
- **授權與隔離 PASS**：/api/me、/api/cases/mine、/api/qa/history 未授權皆 401；/admin、/api/admin/users、/api/auth/login、dev、fieldtest、3 個 API 文件入口、/.env、私人設定路徑、未知路徑／asset 與緊急端點皆 404。保留 backend 真實身分／角色驗證，沒有新增測試登入或權限。
- **本機與正式服務不變**：切換前後 API／Worker PID／啟動時間完全相同；8151 真實 health 維持 ltc_demo、real LINE、心跳正常，仍沿用前輪已證實的 ltc_uat_app／data_demo。正式 8140／Worker、5180、Tailscale Funnel health 正常。通知仍 blocked、緊急派送與 Web Push 關閉，未寫 ltc_clean、未改 LINE 憑證或資料來源。
- 新 proxy log 無重大錯誤。**未執行回復**；原 Page／active record／代理程式快照及操作 log 均保留於 run/uat-private/https-cutover-20261107T135005Z-3113d8/。Mode=uat-proxy 與新 Proxy 身分已記入 run/uat-https-pending/active.json，原 Page 記錄保留供既有恢復工具使用；未重建 Tunnel。新的私人 active-local-uat 記錄亦已更新。

本輪只新增並執行 5 項 allowlist 針對性離線測試及必要公開 smoke checks；未重跑 9／87／60／22 項或完整前後端／DB 套件。原 9 項中的 upload 測試路徑僅改為現有允許的 audio/uploads，以保留 body-limit 測試意圖，沒有重跑該套件。沒有真人登入／綁定／提問或真實緊急通報，沒有建立綁定碼；25 項真人結果仍保持未執行。

**下一步已具備進入 caregiver 真人配對與 UAT 第 1 項的環境條件，但本次沒有授權／執行真人 LINE 操作。** 仍由本人另行授權，按既有 tester_01→caregiver 計畫，使用新 UAT key 產新碼、處理原虛構帳號既有綁定並由本人手機登入確認 role=caregiver；不得沿用舊碼或擅加測試者。本階段至此停止。

LINE 官方 API 語意：[GET Webhook endpoint；404 表示 Channel 沒有設定 URL](https://developers.line.biz/en/reference/messaging-api/nojs/#get-webhook-endpoint-information)。

## 前次：8151 本機 UAT 切換完成（當時 HTTPS 仍為準備頁）

依本次再次授權接續同一次切換，最終結果 SUCCESS_LOCAL_UAT。舊示範 API／Worker 已停止，**新 UAT API／Worker 均已啟動且正常；HTTPS 仍只公開準備頁，未代理 8151，未開始真人驗收。**

- 切換前技術空閒閘門通過：無有效 session、既有示範連線、近期業務稽核、進行中 job／交易或待送通知；正式 8140／Worker、5180、Funnel、準備頁正常。實際停止前核對舊 Python 家族 PID／CreationDate／執行檔，停止只限原示範，不動正式行程。
- **最終備份完成**：停示範寫入後取得完整 ltc_demo.final.dump（保留 owner／ACL，pg_restore --list 可讀），data_demo.final 每檔 SHA256 與來源相同，含專用設定／金鑰版本快照。DB dump SHA256、全部檔案 SHA256 與 manifest SHA256 私存於 run/uat-private/cutover-execution-20261107T132904Z-e5375e/backup-sha256.private.json。未執行任何資料還原，所有預備及最終備份均保留；此備份為 demo，不宣稱已備份正式庫。
- **API／Worker 實際 DB 身分 PASS**：兩者以本次唯一 PGAPPNAME 標記的真實連線確認 datname=ltc_demo、usename=ltc_uat_app、來源 172.18.0.1；使用主目錄 data_demo、UAT 專用 LINE／LIFF 與 private profile。新 API PID 家族 16664, 12148；新 Worker PID 家族 35088, 40040，精確啟動時間／執行檔另私存 active-local-uat.private.json。舊 deploy/demo/run PID 檔只代表已停舊示範，不能拿來管理新 UAT。
- **一次必要本機檢查 PASS**：8151 health db=ok／database_name=ltc_demo／LINE real，公開 config LIFF 與私人 UAT 值一致、dev_features=false，Worker 心跳正常，UAT 帳號實際連 ltc_clean 得明確 HBA reject。未重新執行原 87／60／22／9 項或完整 DB 隔離套件。
- **通知／邊界維持**：UAT_OUTBOUND_MODE=blocked，UAT profile 強制緊急派送與 Web Push 關閉；無正式 LINE fallback，未呼叫 LINE 通知或真人綁定。HBA／PostgreSQL／正式 LINE／Funnel 均未變、未 reload 或 restart，未 migration。沒有建立真實個案或手動新增測試案例，僅允許既定 demo runtime 心跳／工作／保留期處理。
- **周邊服務正常**：正式 8140 及正式 Worker PID／啟動時間與切換前相同，db／心跳健康；5180 /liff=200，正式 Funnel health 正常。5180 前端程序保留，但 UAT 已停用 mock/dev 登入，不能把它視為原 mock 使用體驗仍在。
- **HTTPS 保留準備頁**：現有 trycloudflare /liff 仍為純靜態準備內容，/api/config/public=404；Cloudflare／準備頁沒有被切換或重啟。未開 Webhook。
- **日誌無新增重大啟動錯誤，沒有服務回復、沒有 DB 還原。**

本次控制程序在 Windows 子程序繼承輸出管線處阻塞，但新 API 已啟動並確認身分正常；經即時行程樹／命令／監聽證據區分，自動安全審核允許只停止兩個阻塞的控制 Python（不是 API／Worker），API 未重啟。使用同一執行記錄續接，啟動尚未啟動的 Worker一次，啟動輸出改寫私人檔案，避免管線等待。沒有重試 API 切換、沒有放寬 PID／備份／DB／通知檢查。初次審核拒絕與補證據過程已保留於對話；目前沒有未解的審核阻擋。

實際記錄：run/uat-https-pending/local-cutover-latest.json 指向 SUCCESS_LOCAL_UAT；完整結果／啟動與最小檢查 log 位於上述私人執行目錄。原主工作目錄分支及未提交內容未覆蓋，25 項真人紀錄未變。舊整體切換工具已加「UAT 已啟用則拒絕重跑」保護，後續不可重新跑舊示範交接流程。

**本階段完成並停止。下一步具備另行授權 UAT HTTPS 代理的本機條件；現在尚未對外公開 UAT。** 後續只在新授權下替換 Page、保留既有 Tunnel，代理後再做最小公開檢查；不包含真人綁定、Webhook、通知或三角色驗收。caregiver 優先計畫及單一 tester 配對仍待該階段授權，不能將本次 DB／服務通過填成真人驗收通過。

## 前次：本機切換在停止前中止（歷史；本次已成功）

本次已獲本機切換授權，技術空閒閘門通過：無有效 session、連線、近期業務 audit、進行中工作／交易或待送通知，周邊服務正常。但 Python→Windows PowerShell -Command 的引號傳遞造成 CIM filter 查詢無效，停止前身分檢查即退出；自動回復分支又因 Windows PowerShell 5.1 無法解析無 BOM UTF-8 的既有中文啟動腳本而退出。沒有任何行程被停止或啟動，未執行 DB 還原，不能把分支旗標當成已發生服務回復。

後續只讀核對：原示範 API／Worker PID、CreationDate、執行檔與 listener 完全相同，8151 仍為原 mock；8140／正式 Worker、5180 及 HTTPS 準備頁正常。沒有停寫後最終備份，舊線上預備備份保留。HBA／LOGIN 狀態未變，未切公開代理、未做真人綁定或寫入測試資料。

依「新的重大風險立即停止並回報」要求中止，不自動重試。僅將隔離執行工具改用既有 PowerShell 7 及可審查 UTF-8 腳本檔，避免跨程序雙引號；不含停止／啟動的身分比對與原回復腳本解析均通過。修正後實際切換／回復尚未驗證，不標為通過；主目錄腳本未改。

實際證據見 run/uat-https-pending/local-cutover-latest.json 指向的私人執行目錄。下一步先用修正流程重試本機切換並驗證，之後才有開放 UAT HTTPS 的條件。原 25 項真人結果不變。

## 前次：8151 切換前準備（實際結果以上節為準）

### 現況、差異與中斷範圍

舊站由主目錄 deploy/demo/start_demo_api.ps1、start_demo_worker.ps1 啟動，8151 API 父／子 Python PID 為 28068／3276，示範 Worker 為 9988／12248；另有 conhost 附屬行程，只記錄、不當作應用停止對象。精確 executable／CreationDate／父子關係已私存，執行時必須重新比對，不能只信 PID 檔或名稱。正式 8140 及其 Worker 不在停止範圍，5180 也不需停止（它仍代理 8151，因此 API 換站期間會暫時不可用）。

舊站從主 .env 的 TEST_DATABASE_URL 推導 demo DSN、使用共用 DB 管理者與 LINE_MODE=mock／APP_ENV=development，並開啟 mock 緊急掃描。新站從隔離來源 run/uat-source 啟動，LTC_PROFILE=uat、LTC_UAT_ENV_FILE 指向受限私人檔，強制 ltc_uat_app／ltc_demo／主目錄 data_demo、UAT LINE Channel／LIFF、獨立應用金鑰與目前 UAT HTTPS origin，不回退正式 .env。舊 session／綁定碼因 HMAC key 改變不能沿用；本次唯讀統計沒有有效 session、沒有舊加密草稿，但有 2 個未使用舊綁定碼，不能拿來當 UAT 新碼。

新站必須同時交接示範 Worker：原 Worker 有 retention 清理及工作消費，不能讓舊／新 Worker 共用 demo 資料同時跑。新 worker 會寫 heartbeat、處理工作並清理過期 demo 檔案，未來授權須涵蓋這些 demo runtime 寫入；本輪沒有啟動或寫入。API 啟動沒有 migration／seed／create_all；會初始化其專用健康 token 並預熱既有本機 Ollama，不重啟 LLM／STT。

### 已準備的備份與閘門

私人備份位置 run/uat-private/cutover-prep-20261107T130401Z/：ltc_demo.online.dump（499061 bytes，pg_restore --list 可讀）、data_demo.online-backup（14 檔／101999 bytes，複製期間 metadata 無變化）、原 backend/app、UAT frontend/dist、舊啟動腳本／PID 檔、純靜態準備頁、Tunnel record、UAT 私人環境快照、各項 SHA256 及原行程身分。未複製正式原始 .env 到測試設定，僅記錄其 hash 作回復前漂移檢查。所有備份保留在受限私人目錄，未上傳。

**這是線上預備備份，DB 與檔案不是同一個原子時間點；切換時停示範 API／Worker、確認無其他 demo writer 後，須再做最終 DB dump＋data_demo 一致性備份，不能拿本次線上備份冒稱已達停寫快照。**

本次必要唯讀查詢：有效 demo session=0、queued/running job=0、queued/sending notification=0、既有 audio／TTS／文件路徑超出 data_demo=0。這不證明沒有人正開著 5180 或準備使用示範站；需本人確認短暫維護時段。切換前若這些條件變化，先審核舊工作／檔案，不清空 queue、不刪資料、不強行啟動。

### 可執行啟動／最小驗證工具（本輪只離線檢查）

隔離工作區已準備：

- backend/scripts/check_uat_cutover.py：預設只檢查專用設定、build、blocked／Web Push／緊急封鎖，不接 DB、不登入、不發通知；--live 才對本機新站做 GET，核對專用 token 回報 ltc_demo、real LINE、正確 LIFF、dev_features=false、Worker 心跳；--live --public 才驗證公開 LIFF、設定與最小 health，且 Webhook 仍 404。
- deploy/uat/start_after_approved_stop.ps1：預設 CHECK ONLY；只有另授權後用 -Launch，-Kind api／worker／bridge 明確啟動單一新子行程，私人記錄 PID／建立時間／執行檔與 log；不停止任何既有行程，原示範 Worker 還在則拒絕。run_uat.py 會拒絕占用 8151；worker 必須等舊 heartbeat 超過 90 秒，不能移除保護或手刪 heartbeat。
- deploy/uat/stop_preparation_page_only.ps1：預設 CHECK ONLY，另授權的 -StopPage 只停止 active.json 中身分完全一致、持有 loopback 18551 的 bootstrap 頁，保留既有 Tunnel。
- deploy/uat/restore_preparation_page.ps1：預設 CHECK ONLY，另授權的 -Restore 僅在 18551 空閒且 Tunnel 身分一致時重啟純靜態頁，保留歷史 active record 並更新新 Page 身分，不重啟 Tunnel。
- deploy/uat/https_bridge.py：預設 CHECK ONLY；--launch 才啟動 127.0.0.1:18551，upstream 固定 127.0.0.1:8151，無任意 proxy／8140 目的地；驗證 Host，清除偽造 forwarding／internal token header，僅由代理重建 HTTPS headers；支援串流與有上限的 upload，關閉 access log，使用 trust_env=false，Webhook／文件入口明確 404，錯誤只回一般 502。

本輪新工具 9 項離線測試 PASS（MockTransport，不開 listener、不連 LINE／DB）：固定目的地與 header、Webhook／編碼路徑拒絕、錯誤 Host、docs、body 上限、上游失敗、正式 origin 拒絕、libpq 缺 SQLSTATE 的明確 HBA 拒絕及其他錯誤不可冒充通過。已修正既有啟動 preflight 對 libpq 明確 HBA 拒絕但沒有 SQLSTATE 的相容性問題；不放寬 timeout／錯誤密碼等判斷。新的離線切換檢查 PASS、bridge CHECK ONLY、PowerShell 語法檢查通過。**未執行 --live、--public、-Launch、-StopPage 或 -Restore；未重跑原 87／60／22 與 DB 隔離套件。**

另獲維護切換授權後的順序：

1. 本人確認示範使用者維護時段；核對私人來源／設定／build hash、舊 API／Worker 的 PID＋CreationDate＋executable＋命令標記及正式 PID 排除。保留 HTTPS 準備頁，不開公開代理。
2. 只停止兩個舊示範 Python 行程家族（先子後父），不按名稱殺 Python、不動正式 Worker 或 conhost；確認 8151 空閒、舊示範 Worker 不在，完成停寫後最終 DB／檔案備份並記錄 hash、權限與金鑰版本。
3. 在主目錄執行以下（這是待授權程序，現在未執行）：

```powershell
$uatOps = '.\run\uat-source\deploy\uat'
& "$uatOps\start_after_approved_stop.ps1" -Kind api -Launch
# 等新 API 正常；不對外公開。舊 worker 最後 heartbeat 須超過 90 秒。
& "$uatOps\start_after_approved_stop.ps1" -Kind worker -Launch
& .\backend\.venv\Scripts\python.exe -B .\run\uat-source\backend\scripts\check_uat_cutover.py --env-file 'C:\aa\ltc_care_installer_20260912\ltc_care\run\uat-private\uat.local.env' --live
```

只在新的 API／Worker 子行程、實際 port owner、專用 profile 及 --live 通過後，才保留 UAT 本機服務。任何失敗停止後續，不放寬校驗、不重建 DB、不要直接 start_demo_all（會動到不必要的 5180）。

### HTTPS、LINE 路由與 caregiver 優先

既有 Cloudflare Quick Tunnel 固定轉 18551；要保留網址，不能重啟 Tunnel。另獲公開代理授權後，先保持 API／Worker 已驗證且通知 blocked，只停純靜態 Page，確認 18551 釋放，再用 -Kind bridge -Launch 接手。Tunnel 繼續原樣，網址與 LIFF Endpoint 不變；若 Page 到 bridge 有短暫空窗，可能回 502，不是正式站受影響。不得使用會同時停止 Tunnel 的舊 stop_preparation_https.ps1 作為此步驟。

- Origin：https://office-acids-variety-studio.trycloudflare.com
- LIFF Endpoint：https://office-acids-variety-studio.trycloudflare.com/liff
- Login：LIFF SDK redirect 在 Endpoint 範圍；POST /api/auth/liff 驗證 UAT ID token，不是 LINE Console OAuth callback。不要填不存在的 /auth/line/callback。
- 綁定：POST /api/auth/liff/bind；本次未呼叫。Messaging Webhook 的未來路徑為該 origin/api/line/webhook，但第一階段代理明確封鎖，後台保持 OFF、不按 Verify；沒有 LINE 對話／緊急推播驗收的條件。
- 代理後才執行 --live --public 的唯讀 GET；登入、綁定、提問及其他會寫 audit 的操作不屬於只讀 smoke check，必須另經授權。

一位已授權的 tester_01，先配對既有 caregiver（私人表列 cg_happy_1）；只規劃不寫入，沒有增加真人或改現有帳號角色。本人需確認該人是本階段操作者、UAT Login Channel Roles／openid 與 Console Endpoint 正確；後台仍未直接查證，實際 LIFF 手機登入尚未測。

首次實際配對需另授權 demo 綁定寫入：由本人授權管理者／受控維運以新 UAT HMAC key 產生 caregiver 一次性碼，只交給 tester_01，本人登入並確認回應 role=caregiver。不可重用兩個舊碼，不啟用 dev token、不改角色、不公開碼／User ID。既有 caregiver 舊綁定若須替換，須先記錄並取得授權。

caregiver 結束後，若仍由同一人順序測主管／主任：先由有權限管理者解除前一綁定（既有 unbind 會撤銷 LIFF／dev session 並使未用碼失效），清除手機 session／local storage，再處理目標帳號舊綁定、發新碼與重新 LIFF 登入，確認 session 與角色正確。supervisor／director 舊綁定不能被靜默覆蓋；主任相關產碼／解綁需既有 admin 的受控流程，不能擅自新增 admin 到允許名單。每次操作都需明確授權且留 audit，本輪沒做。

單人順序驗證只能證明各角色操作／拒絕權限；督導轉交的兩端、多使用者同時標註／併發與真實多角色協作，仍需額外授權真人配合，不能把順序操作填成多人 UAT 通過。沿用 04 的 25 項紀錄，不預填結果。

### 回復與不中斷替代方案

回復已備妥為分階段程序，尚未實際演練停止／重啟：

1. 若已切公開代理，先核對新 bridge 的私存 PID／CreationDate／executable／命令及 18551 owner，只停止該新 bridge；使用 restore_preparation_page.ps1 -Restore 恢復純靜態頁，驗證 /liff 為準備頁、/api/config/public=404，原 Tunnel 不動。若 bridge 未切，Page 完全不需停止。
2. 核對新 UAT API／Worker 的啟動私記錄及父子程序身分，只停止新行程；不得套用舊 demo PID 檔來停止 UAT 或正式 Worker。
3. 比對備份中的原主 backend/app／啟動腳本及原 .env hash。主檔未改則直接使用原 deploy/demo/start_demo_api.ps1、start_demo_worker.ps1，從乾淨子程序移除 LTC_PROFILE／LTC_UAT_ENV_FILE 遺留值；不覆蓋主目錄工作。8151 若仍占用或發現來源漂移則停止，不強殺其他行程。
4. **不自動還原 DB 或檔案**：若新 Worker／UAT 操作已寫入或清理 demo，舊金鑰與新產物不能混用；先封存新狀態，由本人決定保留驗收資料或另授權以「同一停寫快照的 demo DB＋data_demo＋對應設定金鑰」成套回復，禁止單獨還原一邊、覆蓋測試成果或觸及 ltc_clean。資料回復不包含在本輪或單純啟動授權。
5. 回復後只做本機 health／mock config 與 Worker 心跳確認；保留備份、UAT 紀錄與失敗原因，不用 git reset/clean、不動 HBA／DB LOGIN。

8151 與 5180 的示範使用者會有短暫中斷，現有 session／碼也會失效。若本人要求示範零中斷，**不要切 8151**；保留整套 demo，另規劃 UAT 專用不同 port＋獨立 DB／資料目錄／Worker／精確 HBA 授權。只換 port 卻共用 ltc_demo／data_demo 不能避免兩套 Worker 與金鑰互相影響；這個替代方案涉及新 DB／權限與啟動，未授權、未實作，不擅自重建系統。

**下一個真正需授權的動作：示範維護時段，停止且只停止舊 8151 API／示範 Worker，做最終停寫備份，再啟動隔離 UAT API／Worker及必要的 demo runtime 寫入並做本機 smoke check。** 本機通過後，再授權只替換 Page 的 HTTPS 代理與 caregiver 產碼／綁定；不把一次啟動當成已授權對外公開或真人寫入。

## 前次：UAT 角色 LOGIN 已啟用，實際 DB 隔離通過（2026-11-07）

依本輪明確授權，只將 ltc_uat_app 改為 LOGIN，未增加任何其他權限。HBA 正式檔 SHA256 仍與已驗證候選相符，解析／前 9 條規則及既有規則後綴／順序無變；相關 PostgreSQL 設定 hash 不變。角色獨立密碼與正式不同，已在本機記憶體核對其 SCRAM verifier 正確，沒有輸出密碼／verifier。

### 本次實際結果

- **demo 正向連線 PASS**：從 127.0.0.1、localhost、::1 三種 UAT 主機寫法各建立新連線；current_database=ltc_demo，current_user=session_user=ltc_uat_app，伺服器看到的來源均為 172.18.0.1，所有驗證交易為 read only。
- **跨庫拒絕 PASS**：列舉所有現有非 demo 資料庫，包含 ltc_clean、ltc_test、postgres 及 templates，另加入不存在的資料庫名稱作拒絕探測；三種來源共 57 次對 19 個目標皆明確回 pg_hba.conf rejects connection，不把錯誤密碼、timeout 或 NOLOGIN 當成隔離通過。
- **最小權限 PASS（依已核准方案）**：demo CONNECT、public schema USAGE；無 DB／schema CREATE，不是 DB／schema owner。35 張既有 public 表逐一驗證 SELECT／INSERT／UPDATE／DELETE 權限；TRUNCATE／REFERENCES／TRIGGER 均不允許，並對每表執行不讀資料列的 LIMIT 0 查詢。4 個 sequence 具 USAGE／SELECT、無 UPDATE。沒有執行 DML、nextval、setval、DDL 或 Migration。
- **角色屬性 PASS**：除 LOGIN 外，NOSUPERUSER、NOCREATEDB、NOCREATEROLE、NOINHERIT、NOREPLICATION、NOBYPASSRLS 不變，無入／出角色成員資格，未改其他 PostgreSQL 使用者或 PUBLIC CONNECT。
- **UAT profile／連線池 PASS**：專用 get_settings 讀入指定私人檔，DATABASE_URL 與該檔一致；既有 UatSettings 只接受 init mapping、不讀正式 env sources。實際呼叫隔離分支 _create_checked_engine 建立獨立連線池並驗證 DB／current_user／session_user 全符合 UAT；未啟動 API／Worker。這不代表舊 8151 已使用新 profile；切換時仍須新程序與新 pool，不可沿用舊 superuser pool。
- **服務持續正常**：8140／8151 前後皆 HTTP 200、db=ok，Worker 心跳正常，兩個 API 及 Worker PID／啟動時間不變。pg_conf_load_time 前後相同，未寫 HBA、未 reload／restart；ltc_clean PUBLIC ACL 前後一致，無正式資料／schema／權限變更。

第一次執行於權限查詢遇到 ProgrammingError（format 的參數型別不明，42P18），安全程序立即恢復 NOLOGIN。保持 NOLOGIN 查明並修正本機驗證工具的參數 CAST 後，再以新連線完成本節檢查；沒有放寬任何條件。第一次失敗與第二次成功紀錄均保留，第一次結果不標為通過。最終所有隔離檢查通過，依授權保留 LOGIN。

本次最新安全索引：run/uat-https-pending/uat-login-latest.json；完整本機執行紀錄：run/uat-private/hba-review-20261107T123743Z/login-verification-20261107T125407Z-bce53d.private.json。資料庫密碼及私人設定均未上傳。未重跑 60／22／87 項既有測試；以上是本次必要的真實 DB 連線與權限驗證。

**DB 面已具備進入 8151 UAT 切換準備的條件，尚未授權／執行實際切換。** 通知維持 blocked，HTTPS 仍僅公開準備頁，Webhook 未啟用。三角色真人配對尚未完成：只有原先 1 位授權測試者，沒有新增身分或更改既有綁定；須本人確認各角色安排並另行授權配對寫入。25 項真人驗收表仍保留原實際結果，未把 DB 驗證記為手機驗收通過。

## 前次：一次性 HBA 已套用並 reload 成功（2026-11-07；當時仍 NOLOGIN）

依本輪明確授權完成，未啟用角色 LOGIN。執行前核對正式 HBA 與原始備份 SHA256 一致、候選與既有 22 項驗證記錄的 hash 一致；容器／映像／postmaster 身分、三種 localhost 路徑的伺服器來源 172.18.0.1 均與預備結果相同。相關非 HBA 設定來源及完整 hash 不變，無解析錯誤、pending restart 或較載入時間更新的設定檔。

- 已在原檔 byte 0 插入先前驗證的 9 條精確 ltc_uat_app 規則；全部原始規則及順序逐項核對保留。容器內先留唯一名稱 cp -p 原檔備份，候選以同目錄暫存檔核對 hash、999:999／0600 後原子替換。私人備份／候選與所有維運記錄保留，未上傳。
- 候選原生語法驗證沿用已通過結果，沒有重跑 60／22／87 套件。實際檔案替換後、reload 前查 pg_hba_file_rules 無錯誤，9 條前綴及原規則後綴／順序完全符合；再核對非 HBA 設定未變。
- 只呼叫一次 pg_reload_conf；日誌確認一次 received SIGHUP, reloading configuration files，無 HBA 載入錯誤。觀測 pg_conf_load_time 更新，持有的原管理連線及全新管理連線 SELECT 1 均成功；未 restart。
- 新 UAT 憑證使用 127.0.0.1／localhost／::1，分別嘗試 ltc_clean／ltc_test／postgres，共 9 次皆得到明確 pg_hba.conf rejects connection。這不是把 NOLOGIN 或網路失敗當隔離證據。demo 連線目前仍因 NOLOGIN 拒絕，尚未驗證 demo 正向登入。
- ltc_uat_app 仍 NOLOGIN，無高權限／繼承變更；ltc_clean 的 PUBLIC ACL 與套用前一致，未改其資料、schema 或權限。未調整其他 PostgreSQL 設定。
- 8140 與 8151 套用前後皆 HTTP 200、db=ok，Worker 心跳正常；API 與四個 Python Worker 行程的 PID／啟動時間完全相同。未重啟服務、切換 8151、改 HTTPS 代理、啟用 Webhook 或通知。
- 未發生異常，未執行回復；原始／候選 hash 及回復程序繼續保留。實際執行紀錄為 run/uat-private/hba-review-20261107T123743Z/apply-20261107T124714Z-76b35f.private.json，伺服器日誌位於同目錄，安全索引為 run/uat-https-pending/hba-apply-latest.json。

**下一階段具備申請啟用 LOGIN 並驗證 DB 的條件，但本次沒有授權／執行。** 另獲明確授權後，先核對 HBA／角色未漂移，再啟用 LOGIN、驗證 demo 的 current_database/current_user/session_user、低權限及必要唯讀查詢，並重驗其他 DB 明確拒絕；失敗維持或恢復 NOLOGIN，不放寬 HBA。真人三角色配對仍未完成，不能以此開始 8151 實際切換或真人 UAT。25 項真人結果保持原狀。

## 前次：pg_hba 變更準備（2026-11-07；歷史，後續已套用）

### 實際環境與精確規則

唯讀確認 PostgreSQL 16.15（Debian），容器 ltc_care-db-1，Windows 55432 轉容器 5432；HBA 路徑 /var/lib/postgresql/data/pg_hba.conf，owner/group 999:999、mode 0600。Windows 使用 127.0.0.1、localhost 或 ::1，三種新連線在伺服器看到的來源皆為 172.18.0.1；localhost 解析含 ::1 及 127.0.0.1。容器內 loopback 為不同路徑，不能將 Windows localhost 與伺服器來源混為一談。未變更 Docker 發布埠或網路。

現有有效規則依序為：117 local all/all trust、119 IPv4 loopback trust、121 IPv6 loopback trust、124～126 physical replication trust，128 host all/all/all scram-sha-256；規則無解析錯誤、無 include，依 rule_number 確認順序。建議將以下完整區塊插在檔案 byte 0，早於所有現有規則／include；既有檔案作完整原樣後綴保留，不改正式帳號規則：

```conf
host ltc_demo ltc_uat_app 172.18.0.1/32 scram-sha-256
host ltc_demo ltc_uat_app 127.0.0.1/32 scram-sha-256
host ltc_demo ltc_uat_app ::1/128 scram-sha-256
host all ltc_uat_app 0.0.0.0/0 reject
host all ltc_uat_app ::/0 reject
host replication ltc_uat_app 0.0.0.0/0 reject
host replication ltc_uat_app ::/0 reject
local all ltc_uat_app reject
local replication ltc_uat_app reject
```

前 3 條允許實測 Docker 閘道及容器內兩個 loopback 僅連 demo，全部要求 SCRAM；後 6 條攔截該角色的所有其他 TCP／Unix socket 與 physical replication。host 同時涵蓋 SSL／非 SSL。使用精確角色名稱，不使用 all 或 +群組。PostgreSQL 採第一條符合規則，驗證失敗不繼續向後嘗試；因此錯誤密碼或明確 reject 不會落入後方 trust。all 不匹配 physical replication，故另列 replication 拒絕。

### 已完成的備份與非正式驗證

完整備份位於主專案忽略目錄 run/uat-private/hba-review-20261107T123743Z/：pg_hba.conf.original、pg_hba.conf.candidate、uat-block.conf、manifest.private.json；另有 postgresql.conf 與 postgresql.auto.conf 完整快照／雜湊、檔案權限及容器／版本／來源記錄。這是設定備份，不是正式資料庫備份。原始 HBA 5743 bytes，候選只增加前綴，原檔後綴逐位元相等；原始及候選 SHA256 已記錄。備份未上傳、未刪除。

- 60 個離線規則案例通過：已允許來源／其他來源、demo／clean／test／postgres／其他庫、IPv4／IPv6、Unix socket／複寫及其他角色略過新增區塊。
- 以已安裝相同不可變映像建立全新 tmpfs PostgreSQL：無網路、無公開埠、未掛任何正式資料卷，只讀掛入完整候選 HBA。原生解析無錯誤，22 項測試通過，包括 demo SCRAM 正向／錯誤密碼、clean／test／postgres／template1 的明確 HBA reject、IPv6／physical replication／Unix socket 拒絕，以及代表既有 ltc／postgres 帳號的測試角色仍匹配原 trust。測試角色與資料庫均為全新虛構內容，未複製正式憑證或資料；臨時容器已獨立停止／移除，紀錄保留。
- 172.18.0.1 正向來源已由實際唯讀連線確認，候選匹配由離線矩陣驗證；沒有把此來源上的正式 UAT SCRAM 登入標為通過。正式檔案未寫入、未 reload、角色仍 NOLOGIN。
- 只檢查本次變更的 60＋22 案例，未重跑原 87 項或完整套件。

### 其他角色／連線池繞過檢查與限制

UAT DSN 明確為專用角色／ltc_demo、沒有 URL query override；UatSettings 僅讀指定私人檔、不回退正式 .env；程式連線入口只見 SQLAlchemy 直連，連線時檢查 current_database/current_user 與危險角色權限，沒有 SET ROLE 或外接 PgBouncer 路徑。實際終點及容器確認是 PostgreSQL，現有 client sessions 僅既有正式角色，沒有已啟用的 UAT pool。ltc_uat_app 無入／出角色成員資格、無角色專用設定；demo 無 dblink／postgres_fdw extension、foreign server、user mapping 或應用 SECURITY DEFINER 函式。

這不代表 HBA 可以阻止持有另一個正式 DB 帳密的人以正式角色登入，亦不能阻止 superuser 主動 SET ROLE；精確角色規則只約束連線提出的角色。8151 切換時必須使用新 UAT profile／全新連線池，唯讀確認 current_user 與 session_user 都是 ltc_uat_app，不能重用目前舊 superuser pool。本輪沒有切換服務或改權限。

### 一次性套用程序（待另外授權；本輪完全未執行）

1. 保持 UAT NOLOGIN 與通知 blocked；以指定容器 ID、映像 ID、postmaster_start_time、HBA 路徑及目前 SHA256 核對 manifest。任何差異、角色屬性變化或來源路由變化即停止，不自行改規則重試。
2. 以管理者建立並保留唯讀連線，記下該 backend PID，做 SELECT 1。確認可用 Docker exec 的本機復原路徑。核對所有相關設定檔的來源集合及雜湊與備份相同；本次原始檢查為無解析錯誤、無 pending_restart，兩個 config 檔案時間均不晚於 pg_conf_load_time。套用前若有其他尚未載入的設定變更即停止；pg_reload_conf 會要求全部設定重讀，不能只顧 HBA。
3. 在容器內另建唯一名稱的原檔 cp -p 備份，驗證與 original SHA256 一致。以同目錄唯一暫存檔接收私存候選，確認 SHA256、owner/group 999:999、mode 0600，再原子 rename 到原 HBA 路徑。避免逐行修改、截斷正式檔案或直接覆蓋既有備份；rename 前再次檢查目標仍等於 original hash。
4. reload 前以現有管理連線查 pg_hba_file_rules，必須無 error、前 9 條精確等於候選、其餘規則與原檔相同，並再次核對非 HBA 設定 hash。若不符，直接依下方回復，不能載入錯檔。
5. 明確授權後只呼叫一次 SELECT pg_reload_conf()，不重啟；true 只表示訊號已送出，不代表 HBA 已成功載入。查日誌的 reload 結果／錯誤、pg_hba_file_rules 及現有連線 SELECT 1；開一條既有正式角色的全新唯讀連線 SELECT 1，確認新連線仍可用，不做業務寫入或登入。
6. ltc_uat_app 仍 NOLOGIN：先用新憑證對三種 host 寫法連 clean／test／postgres，須得到明確 HBA reject，不把 NOLOGIN、timeout 或密碼錯誤當跨庫隔離通過。demo 預期仍因 NOLOGIN 拒絕；本輪／這個套用程序不允許 ALTER ROLE LOGIN。
7. 成功則保留候選、備份、SHA256、日誌、連線與角色檢查結果。只有另外取得啟用 LOGIN 的授權後，才能再測 demo 正向／其他庫負向及既有 --check-db；之後才討論 8151 切換。不能因 HBA 套用成功就標記真人 UAT 或角色配對完成。

### 失敗與回復程序（待授權；不反覆編修）

任何新正式連線失敗、HBA reject 未符合預期、reload 未確認成功或解析錯誤：停止後續步驟、保持 NOLOGIN，不重啟、不重試改規則。保留管理連線及錯誤紀錄。若現有 HBA SHA256 精確等於候選 hash，將原始完整備份寫到同目錄唯一暫存檔，驗證 original hash 及 999:999／0600，再原子 rename 回原路徑；保留候選與所有備份。若 HBA 已有第三種 hash，表示可能有他人變更，停止自動還原、交由負責人比對，避免覆蓋工作。

回復原檔後查 pg_hba_file_rules 無 error，只有在原核准的回復範圍內 reload 一次，再驗證既有管理連線與全新正式角色唯讀連線、角色仍 NOLOGIN及原始 hash 一致。若 reload 本身拒載錯誤 HBA，Linux 伺服器通常仍沿用先前有效規則，但不能以此假設取代新連線驗證。失敗後不自動啟用 LOGIN、不刪角色或備份。

### reload 的邊界與目前結論

此伺服器是 Linux 容器，需 SIGHUP／pg_reload_conf 才重讀 HBA，不能套用 Windows 原生 PostgreSQL「檔案修改即影響下一條新連線」的例外。HBA reload 不切斷或重新驗證既有連線；之後的新連線採新載入規則，故連線池重用舊 session 不能當 HBA 新連線測試。此次區塊只匹配專用 UAT 角色，既有 8140／ltc_clean 角色與資料不變；殘餘風險為路由／排序錯誤、檔案權限或解析失敗，以及 reload 順便載入其他待生效設定，已設置 hash／來源／解析／新連線／單次回復關卡。

**具備一次性套用的準備條件；仍須本人明確授權寫 HBA 與 reload（含失敗回復）。尚未具備啟用 LOGIN 或切換 8151 條件。**

官方依據：[PG16 HBA 第一條符合規則、include、reload 與 Windows 例外](https://www.postgresql.org/docs/16/auth-pg-hba-conf.html)、[pg_reload_conf 訊號及設定檢查](https://www.postgresql.org/docs/16/functions-admin.html#FUNCTIONS-ADMIN-SIGNAL)。

## 前次授權執行：本機設定與 DB 角色預備（2026-11-07；歷史）

本節為最新狀態；下方保留前次唯讀結果，不能把前次的缺欄位／角色不存在當成現況。

- **本機設定完成**：PUBLIC_BASE_URL 已填目前 Quick Tunnel origin，未修改 LIFF ID 或其他 LINE 憑證。新 DB 密碼由安全亂數產生，只寫本機私人設定；PostgreSQL 接收 SCRAM verifier，未把明文密碼放 SQL。既有私人設定先保留於同一受限私人目錄內的備份，未上傳。uat.local.env 與配對紀錄 ACL 核對僅本人及 SYSTEM。
- **既有靜態預檢 PASS（exit 0）**：設定完整與靜態隔離通過；不是部署、DB 可用、LINE 憑證有效或三角色真人驗收通過。未重跑 87 項測試。
- **角色已建立，但禁止登入**：ltc_uat_app 為 NOLOGIN、NOSUPERUSER、NOCREATEDB、NOCREATEROLE、NOREPLICATION、NOBYPASSRLS、NOINHERIT，無其他角色成員資格。只新增 ltc_demo 的 CONNECT、public schema USAGE、既有 public 表 SELECT／INSERT／UPDATE／DELETE、序列 USAGE／SELECT。逐表逐項權限檢查通過，無 schema CREATE 權限，未改 schema 的 PUBLIC 授權、未寫入應用資料。
- **跨庫隔離尚未完成**：查得 ltc_clean 的 PUBLIC CONNECT 仍存在。只授予 demo 權限無法覆蓋該繼承權限，故未啟用 LOGIN。用新憑證實際連線 ltc_demo 與 ltc_clean 均因 NOLOGIN 拒絕；這只能證明角色目前不可登入，不能冒充「只准 demo」的資料庫邊界測試成功。沒有修改 ltc_clean、全域 PostgreSQL 設定或執行 reload／restart。
- **配對仍待本人確認**：只保留既有 1 位授權測試者，不新增人員、不把同一身分擅自分派三角色。照服員、居督、主任三個既有虛構帳號均啟用且角色／機構相符，但既有綁定皆未匹配該授權 ID。各帳號 assigned_tester 維持未指定；詳細對應準備表在私人目錄 uat.role-pairing-status.json，以 tester_01 指向現有允許名單第 1 位，不在文件公布 ID。
- **通知仍 blocked**；未重啟任何服務、未切換代理或啟用 Webhook。25 項真人結果未變。

**8151 可以進入離線切換計畫／指令審閱準備，但不能實際切換或開始真人 UAT。** 下一個維運授權需明確允許先前方案的「僅針對 ltc_uat_app 的 pg_hba allow／deny 規則及 reload」，在現有廣泛規則之前只准本機 ltc_demo、拒絕其他資料庫及來源；保留所有既有正式角色規則，不需重啟。這是全域設定檔變更，目前明確未獲授權，因此沒有執行。完成邊界後才可另經授權啟用 LOGIN，並以 UAT 憑證實測 demo 可連、clean／test／postgres 拒絕。本人亦須先確認現有授權測試者的角色及其餘角色如何由授權真人承擔，之後再單獨授權 demo 配對寫入。不得以未授權身分補足名單。

安全執行摘要：run/uat-https-pending/db-stage-safe-result.json；執行腳本 stage_uat_db.py 為一次性預備工具，角色已存在後會拒絕重跑，不能拿來啟用 LOGIN。未將憑證、私人檔案或配對資料提交 GitHub。

## 前次唯讀預檢：LIFF ID 填入後（2026-11-07；歷史）

本節取代下方較早的「憑證及 HTTPS 尚缺」準備紀錄；歷史紀錄保留。沒有重跑已通過的 87 項測試，沒有登入、建立綁定碼、發送訊息、切換代理或修改資料庫。

| 檢查 | 本次實際結果 | 尚缺條件 |
|---|---|---|
| 既有靜態預檢 | NOT_READY: UAT_DATABASE_CREDENTIAL_REQUIRED | DATABASE_URL 仍含新 UAT 密碼占位值；不可用正式密碼替代 |
| LINE 四項本機設定 | PASS：Login Channel ID、LIFF ID、Messaging secret／access token 均已填且不同於正式指紋；LIFF ID 前綴符合 Login Channel ID | 僅靜態檢查，未向 LINE 驗證憑證有效性、Provider 或後台設定 |
| 正式指紋／新應用密鑰 | PASS：基準與目前正式來源一致；三個新應用密鑰不同於正式 | 不代表既有 8151 已載入這些設定 |
| 測試者名單 | 三角色 UAT 尚不完整：目前只有 1 個格式有效、唯一的測試者 ID | 補齊三位指定測試者，並在本機確認本人身分及角色對應；名單不公開 |
| 三角色虛構帳號 | PASS：設定中的照服員、居督、主任帳號均存在、啟用、角色相符且同機構 | 三者既有綁定皆未對應目前允許的測試 ID；不得將既有綁定當成新真人測試者配對完成；後續配對需另行授權 |
| 通知 | PASS：UAT_OUTBOUND_MODE=blocked | 維持 blocked；這是未部署 profile 的設定結果，不是對舊 8151 執行中設定的重新驗證 |
| 公開 HTTPS | PASS：準備頁 /liff 回 HTTP 200；網址仍為 https://office-acids-variety-studio.trycloudflare.com | 本機 PUBLIC_BASE_URL 尚為占位值，需填該 origin；LINE Console 的 Endpoint 未直接查證 |
| 準備頁／Tunnel 行程 | PASS：兩行程 PID、啟動時間、執行檔及專用命令標記與 active.json 相符；純靜態頁仍只監聽 127.0.0.1:18551 | 未代理 8151；沒有停止或重啟任何行程 |
| 最小權限 DB | 腳本準備完成，實際權限尚未就緒；ltc_uat_app 不存在，data_demo 目錄存在 | 管理者核准建立角色、新密碼、僅 ltc_demo 的 grants、精確 pg_hba 邊界及 reload 後，才可驗證跨庫拒絕 |

LIFF 應使用的完整 Endpoint：`https://office-acids-variety-studio.trycloudflare.com/liff`。本次只確認該網址實際可達且與現有 Tunnel 記錄一致，**沒有聲稱 LINE Developers Console 已設定一致**。請本人核對既有 LIFF App Endpoint；不填不存在的 OAuth callback，Messaging Webhook 保持停用、不按 Verify。

先由本人依既有私人指引補齊 PUBLIC_BASE_URL、其餘測試者及配對規劃。下一個需要授權的維運動作為 DB 最小權限部署：審核 `deploy/uat/least_privilege.sql.example` 與 `pg_hba.conf.example`，建立新角色及僅 demo 的應用權限、設定新密碼、限定連線邊界並 reload PostgreSQL 設定；不修改 ltc_clean 權限／資料。SQL 內的 public schema CREATE 撤權會影響 ltc_demo 其他使用者，須納入授權審核；腳本仍是草稿，未執行。此授權不含重啟服務、真人配對寫入、切換公開代理或啟用 Webhook，這些須另行核准。

本輪安全狀態摘要僅存於忽略目錄 `run/uat-https-pending/uat-latest-readonly-status.json`，不含憑證或測試者 ID。25 項真人驗收結果未改，仍不得開始第 1 項真人登入／綁定。

## 本機設定接續紀錄（尚未啟動；歷史）

使用者已告知建立 UAT 專用 Provider「小照 UAT 測試」、測試官方帳號、Messaging API、LINE Login 與 LIFF。本輪沒有登入後台驗證參數，也沒有要求回傳機密。

- 隔離程式已固定放到主專案的 `run/uat-source`（commit acabff64fe4e7c38b38193e7045e482325e761f4），與主目錄分支分開；沿用既有 build，未重跑完整測試。
- 私人設定 `run/uat-private/uat.local.env` 已建立；全新應用密鑰與正式單向指紋已準備，沒有覆蓋正式 .env 或複製正式憑證。
- 請只依同目錄「本機設定指引.md」一次填寫 LINE 四項、受測者 ID、角色對應，及稍後選定的 UAT HTTPS／新 DB 角色密碼。指引含實際本機路徑與安全預檢命令，不必再重建前面的手冊。
- 私人目錄只給本人修改及 SYSTEM 完整控制，已被主專案 run/ ignore 排除；未上傳設定、指紋或指南中的任何私人值。
- 唯讀確認 ltc_demo 與 data_demo 存在，目錄與 data_clean 不同；ltc_uat_app 尚未建立，最小權限仍不具備。
- 靜態預檢正確回 NOT_READY（DB 密碼 placeholder 尚在），沒有回退正式設定；LINE 憑證／人員名單及 HTTPS 尚待本機填入。
- 通知設定維持 blocked；沒有新增公開入口、重啟任何服務、產碼、登入、寫 DB 或發送 LINE 訊息。原 25 項真人結果未變更。

## 1. 沿用環境及回呼分流

| 元件 | 正式環境 | 新 UAT 方案（未啟用） |
|---|---|---|
| API | 原 8140，不更動 | 沿用 8151；未來另經授權將 API／Worker 切到隔離分支程式與專用 profile，不同時啟兩個示範 Worker |
| DB／資料目錄 | ltc_clean／data_clean | 沿用 ltc_demo／data_demo；改用未建立的 ltc_uat_app 最小權限角色，獨立應用密鑰 |
| 前端 | 正式入口 | 公開 UAT 同源由 8151 託管隔離工作區 frontend/dist；5180 只留本機開發，代理固定指向 8151 |
| LINE Provider／Channel | 原設定保留 | 建立測試專用 Provider；UAT Messaging API 與 UAT LINE Login 放在同一個 UAT Provider，不使用正式 Channel／Token／LIFF |
| LIFF／HTTPS | 原正式 LIFF／Funnel 保留 | 新 UAT LIFF ID；新獨立 HTTPS 主機（下稱 UAT_ORIGIN），不共用正式域名路徑前綴 |
| LIFF Endpoint | 不更動 | UAT_ORIGIN/liff；SDK 導回同一 UAT 來源的 /liff 及其子路徑 |
| 登入驗證 | 不更動 | 既有 POST /api/auth/liff 只用 UAT Login Channel 驗證 ID Token；沒有新增 OAuth code callback 端點 |
| Webhook | 不更動 | UAT_ORIGIN/api/line/webhook，只用 UAT Messaging secret 驗簽並限制來源 userId 名單，拒絕 group／room |
| 反向代理 | 不更動 | deploy/uat/Caddyfile.example 僅草稿：獨立 UAT_HOST 的全部路由轉 127.0.0.1:8151，保留 Host／HTTPS 來源；不改現有 Funnel |

目前 8151 仍是舊 mock 行程。本輪沒有切換或重啟；「可以沿用 8151」是部署方案，不代表現在已能用真實 LINE 登入。獨立 HTTPS 可由負責人之後選定的既有代理／測試網域提供，範例不會自動申請網域、啟動 Caddy 或增加 Funnel。

## 2. LINE Developers 人工操作：集中一次辦理

以下只操作**新建 UAT 專用資源**，不改正式資源；本輪代理沒有代操作或發送通知。

1. 在 LINE Official Account Manager 建立明確標示「UAT／僅虛構資料」的測試官方帳號，啟用 Messaging API 並選新 UAT Provider。取得測試 Messaging Channel secret／access token，僅填本機私人設定檔。測試帳號的自動回應／歡迎訊息先停用，避免平台自行對受測者送訊息；不要讓既有嘉安正式官方帳號代替它。
2. 在同一 UAT Provider 建立 Web 類型 LINE Login Channel；將三位指定測試者加入 UAT Channel Roles，依後台開發狀態確認各自可登入。記下 UAT Login Channel ID，不沿用正式 ID。不同 Provider 下的 LINE userId 不能直接照抄，請測試者核對 UAT Provider 內本人 ID。
3. 在 UAT Login Channel 的 LIFF 頁新增應用：Full、Endpoint=`UAT_ORIGIN/liff`，scope 至少 `openid`，不需要 email 或 chat_message.write；profile 僅於確實需要時加。取得新的 UAT LIFF ID。若需要設定 Web 登入 redirect，僅設定 UAT 來源；現有應用採 LIFF SDK，不填不存在的 `/auth/line/callback`。SDK 的 redirectUri 須落在 LIFF Endpoint URL 範圍，不能導向正式站。
4. 等測試 HTTPS／專用 profile 的部署另獲核准後，僅在 UAT Messaging Channel 填 Webhook=`UAT_ORIGIN/api/line/webhook`；確認測試帳號自動回應仍停用。此時才由負責人核准 Verify／Use webhook 的連通驗證，不能在現在把未部署端點標正常。UAT LINE Login 若連結官方帳號，只選剛建的測試帳號。
5. 三位測試者各自確認手機、UAT Channel Roles，從 UAT Channel Basic settings 的 Your user ID 取得本人在該 Provider 的 ID，私人填入 `UAT_LINE_USER_IDS`；不把 userId、Token、綁定碼、密碼貼到 GitHub 或回報表。

官方依據：[Messaging API 建立流程](https://developers.line.biz/en/docs/messaging-api/getting-started/)、[新增 LIFF／HTTPS 與 openid](https://developers.line.biz/en/docs/liff/registering-liff-apps/)、[LIFF login redirectUri](https://developers.line.biz/en/reference/liff/#login)、[Webhook 原始 body 驗簽](https://developers.line.biz/en/docs/messaging-api/verify-webhook-signature/)、[Provider 與 userId](https://developers.line.biz/en/docs/messaging-api/getting-user-ids/)。以上是準備指引，不代表後台已設定。

## 3. 你只需集中填這些資訊

| 欄位 | 來源／用途 |
|---|---|
| UAT HTTPS 主機／PUBLIC_BASE_URL | 新測試網域或經核准的獨立 HTTPS 入口，不是正式 Funnel，也不是手機的 localhost |
| LINE_LOGIN_CHANNEL_ID、LIFF_ID | 新 UAT Login Channel／LIFF |
| LINE_CHANNEL_SECRET、LINE_CHANNEL_ACCESS_TOKEN | 新 UAT Messaging Channel，與正式值不同 |
| UAT_LINE_USER_IDS | 三位指定受測者在 UAT Provider 下的本人 ID，私人逗號分隔名單 |
| UAT_ACCOUNT_ROLES | 現有虛構帳號→預期角色；範例沿用 cg_happy_1、sup_happy_a、director_happy。需 S2／admin 協作時才加入既有受控身分，不改資料庫角色 |
| DATABASE_URL | 未來核准建立的 ltc_uat_app、獨立新密碼、ltc_demo；不能用現在共用 superuser 或正式密碼 |
| UAT_PRODUCTION_FINGERPRINTS_FILE | 本機產生的正式設定單向指紋檔；不是正式原始憑證副本 |
| SECRET_KEY／DATA_ENCRYPTION_KEY／INTERNAL_HEALTH_TOKEN | init_uat_private.py 產生全新值，不需從正式複製 |

## 4. 專用設定／預檢（以下是未來由本人執行的命令，不是本輪已執行）

使用既有 backend/.venv 的 Python，不升級或重建；命令中的 WORK 指隔離工作區根目錄，MAIN 指目前正式專案根目錄。私人檔建議放 WORK/deploy/uat/private，已被 gitignore 排除。Windows 先由本人確認私人目錄 ACL 只允許本人及必要管理者，再填憑證；不要使用共用同步資料夾。

①現在執行（先準備私人檔案，不啟動服務）：

```powershell
# 僅範例，先將 WORK／MAIN 填為本人確認的路徑；不在主目錄套用 git checkout。
$workRoot = '隔離工作區絕對路徑'
$mainRoot = 'C:\aa\ltc_care_installer_20260912\ltc_care'
$pyUat = Join-Path $mainRoot 'backend\.venv\Scripts\python.exe'
$privateUat = Join-Path $workRoot 'deploy\uat\private'
& $pyUat (Join-Path $workRoot 'backend\scripts\init_uat_private.py') --output (Join-Path $privateUat 'uat.local.env')
# 正式值只在記憶體比較／做單向指紋，不複製到 UAT 設定，也不印出。
& $pyUat (Join-Path $workRoot 'backend\scripts\check_uat_env.py') --make-baseline (Join-Path $privateUat 'production-fingerprints.json') --production-env (Join-Path $mainRoot '.env') --production-health-token-file (Join-Path $mainRoot 'deploy\fieldtest\run\internal_health_token.txt') --production-origin 'https://stust.tail379935.ts.net'
```

兩工具拒絕覆寫既有檔案。之後只在私人 uat.local.env 填完第 3 節欄位；範例的 REPLACE 值故意不可用，不能當作就緒。啟動只讀此專用檔，會忽略父行程的正式 DATABASE_URL、LINE 憑證及根 `.env`，並比較指紋拒絕共用值（包括資料庫密碼）。

②成功後執行（明確的唯讀預檢；不產碼、不送訊）：

```powershell
& $pyUat (Join-Path $workRoot 'backend\scripts\check_uat_env.py') --env-file (Join-Path $privateUat 'uat.local.env')
# DB 角色／連線限制另獲核准且備妥後才做以下唯讀連線檢查。
& $pyUat (Join-Path $workRoot 'backend\scripts\check_uat_env.py') --env-file (Join-Path $privateUat 'uat.local.env') --check-db
# UAT Webhook 後台設定完成後，唯讀 GET 它的設定；不是 Verify 的事件 POST。
& $pyUat (Join-Path $workRoot 'backend\scripts\check_uat_env.py') --env-file (Join-Path $privateUat 'uat.local.env') --check-line
# 無 --launch 時只有靜態檢查，不啟動任何服務。
& $pyUat (Join-Path $workRoot 'backend\scripts\run_uat.py') --env-file (Join-Path $privateUat 'uat.local.env') --kind api
```

`--check-db` 強制唯讀交易：核對角色權限、既有三角色同機構、schema 不可 CREATE，並用同一 UAT 帳號確認 ltc_clean／ltc_test／postgres 都拒絕連線；網路失敗不冒充權限拒絕。`--check-line` 只讀 Messaging API Webhook 設定，不確認 LIFF Console 或手機登入，不送通知。所有輸出只列狀態碼，不列憑證／帳號內容。

③失敗後執行：保存 NOT_READY 代碼；不回退讀正式 `.env`、不換回 superuser、不把 mock 測項改成真人通過。缺少角色／憑證／路由則保持未部署，集中交負責人處理。

## 5. 最小權限資料庫方案（只有範例，沒有執行）

- `deploy/uat/least_privilege.sql.example`：新 ltc_uat_app，不是 DB／schema owner，無 superuser／CREATEDB／CREATEROLE／REPLICATION／BYPASSRLS／角色繼承；只授 ltc_demo 內應用需要的 DML 與 sequence 權限，不給 DDL 或 Migration。
- `deploy/uat/pg_hba.conf.example`：在廣泛 allow 規則**之前**，只准 ltc_uat_app 連本機 ltc_demo，對其他資料庫／來源明確 reject，包含 IPv4、IPv6 與本機 socket。若 PostgreSQL 在 WSL／容器，需由管理者把 allow 來源換成實際測試連線的精確位址／CIDR，不能直接開放全部來源；預檢仍須確認跨庫拒絕。
- PostgreSQL 沒有以個別 REVOKE 覆蓋 PUBLIC CONNECT 的 DENY 規則；所以不能只對 ltc_uat_app 執行 REVOKE CONNECT 就宣稱阻隔正式 DB。方案不動 ltc_clean 權限，改以角色及 pg_hba 的精確邊界，再實測拒絕連線。
- 建立角色、修改 ltc_demo schema grant、pg_hba 與 reload 都屬之後需另行核准的維運動作。本輪沒有執行任何 SQL 範例，也沒有改兩個資料庫的資料／權限。

## 6. 三角色帳號及綁定

1. 優先沿用既有虛構三角色。私人 `UAT_ACCOUNT_ROLES` 明確列帳號及既有角色，執行時拒絕未列身分及角色不符者；預檢只讀確認存在、啟用及同機構，不建立或改角色。
2. 新應用密鑰會使舊 session／綁定碼失效；新的資料加密 key 也不能讀舊未確認的加密草稿／LINE 事件。**保留舊資料，不複製正式 key 來解密**。舊佇列若來源／帳號不在名單會略過；新 UAT 只建立新的虛構錄音／提問，需另有 ltc_demo 寫入授權。
3. 需產 UAT 綁定碼時，由受控既有 admin／可核發本人碼的居督依現有規則處理。若要 admin 協助，先把該既有虛構 admin 納入私人 roster，透過本人已有密碼登入 UAT 後台；不共用帳號或改正式角色。主任目前不能直接核發綁定碼的限制維持。
4. 居督／主任若已有不明用途或舊合成 LINE 關聯，先記阻擋。只有之後本人明確批准對**示範帳號**解除／重綁後，才能用指定測試者的 UAT Provider 身分重新綁定；本輪不解除、不產碼。
5. 最初只驗 LIFF 的真實登入、角色顯示與網頁功能。LINE 聊天室 reply 與內容下載在 UAT 仍封鎖；語音用 LIFF 的既有上傳功能。不可把這些限制誤記為聊天室端到端已通過。

## 7. 通知及啟用邊界

- `UAT_OUTBOUND_MODE=blocked` 預設封鎖所有 LINE 外送。reply 一律封鎖。非名單來源不能登入／綁定或進 Webhook 工作；group／room 拒絕。
- 日後只有另行准許測試推播，才把私人設定改成 allowlist；一般 push 還需 recipient 精確在 `UAT_LINE_USER_IDS`；舊通知內的正式站／舊 localhost／別的 LIFF 連結也會被拒絕，只允許本 UAT HTTPS 或本 UAT LIFF 連結（其餘來源請在網頁內查看）。本輪沒有切換、沒有發送，名單不能包含未指定的真實嘉安收件人。
- 緊急通知掃描、舊緊急工作及 Web Push 在 UAT 強制封鎖；即使父行程意外繼承 on 也不啟用。訂閱 Web Push 路由亦拒絕。不驗背景響鈴、鎖屏、斷網送達或真實緊急通報。
- UAT launcher 停用 uvicorn access log，Caddy 範例也不啟用完整 URI 存取日誌，避免記錄 LIFF 回呼 query。新入口僅提供新的 UAT host，不讓舊正式 LIFF 或不同 Origin 進 UAT。本機只放行公開健康／設定 GET，不能用 loopback 當成繞過真實登入的入口。切到 UAT profile 後，5180 僅作本機靜態版面開發；真人互動必須走 UAT HTTPS，不能把 5180 當 LINE 回呼入口。

未來啟用仍需另外授權：備妥獨立憑證／HTTPS、DB 最小權限、受控配對與寫入範圍後，先確認隔離前端 build 產物，再由負責人安排既有示範 API／Worker 的受控切換。run_uat.py 只有明確 `--launch` 才執行；8151 已占用或已有近期 Worker 心跳會拒絕，不停止舊行程、不自動重啟。這個開關本輪沒有執行。不能把隔離 commit 複製覆蓋主工作目錄來部署。

## 8. 驗證紀錄

- 專項離線測試：87 項通過（mock HTTP、模擬 DB cursor／連線；未連 ltc_demo／ltc_clean，未呼叫真實 LINE）。
- 隔離前端 Vite build 成功；產物位於隔離工作區 frontend/dist，未部署、不提交產物。
- 空白設定範例回 NOT_READY（預期拒絕），未回退正式設定。
- 原本後端 356、前端 213 與維運 19 項完整套件沒有重跑。
- 待驗：新 UAT Channel／LIFF 後台、實際 DB 最小權限、實際 HTTPS 與回呼、API／Worker 載入、三角色手機登入與綁定、25 項真人驗收；均尚未標通過。

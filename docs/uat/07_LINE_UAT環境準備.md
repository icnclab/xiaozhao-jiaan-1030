# LINE／LIFF UAT 隔離環境準備

2026-11-07；本文件對應隔離分支 `uat/line-isolation-20261107`，基底 `b693e0f5d5052b7f2162edc83125f76fefe9f7a0`。程式與範例已準備，**尚未部署、未取得測試 LINE 憑證、未建立 DB 角色、未修改任何資料、未進行真人驗收**。25 項結果仍使用 [04 驗收勾選表](04_驗收勾選表.md)，不另開結果表。

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

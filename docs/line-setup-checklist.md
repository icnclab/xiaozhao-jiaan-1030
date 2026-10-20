# 真實 LINE 串接：操作清單（本機 Quick Tunnel 實測版）

> 分工：**A 段只有你能做**（建 channel、複製 secret／token）；**B 段由腳本代勞**。密鑰只貼進 `F:\ltc_care\.env`，不要貼進對話。

## A. 你在 LINE Developers Console 做的事（約 15 分鐘）

登入 <https://developers.line.biz/console/>（用團隊的 LINE 帳號；建議由學生組長的帳號建立，未來交接方便）。

### A1. Provider
- Create a new provider → 名稱例如 `STUST-LTC`。**之後兩個 channel 都建在這個 provider 底下**（跨 provider 的 userId 不一致，帳號會對不上）。

### A2. Messaging API channel（bot）
1. 在該 provider 下 Create channel → **Messaging API**。Channel name 例如「小照｜長照照護小幫手（測試）」；類別選 醫療／健康 之類即可。
2. 建好後：
   - **Basic settings → Channel secret** → 貼到 `.env` 的 `LINE_CHANNEL_SECRET=`
   - **Messaging API → Channel access token (long-lived) → Issue** → 貼到 `LINE_CHANNEL_ACCESS_TOKEN=`
3. 同頁把 **Auto-reply messages** 設 Disabled、**Greeting message** 設 Disabled（bot 自己會回歡迎訊息）。
   （這兩項會跳到 LINE Official Account Manager 的「回應設定」：回應模式＝**聊天機器人**、自動回應＝關、Webhook＝開。）
4. **Webhook URL 先留空**，等 B 段拿到 tunnel 網址後由腳本設定。

### A3. LINE Login channel（LIFF 用）
1. 同一 provider 下 Create channel → **LINE Login**。App types 勾 **Web app**。
2. **Basic settings → Channel ID**（純數字）→ 貼到 `LINE_LOGIN_CHANNEL_ID=`。
3. **LIFF 分頁 → Add**：
   - LIFF app name：`小照`
   - Size：**Full**
   - Endpoint URL：先填 `https://example.com/liff`（占位，B 段會給真正網址再改）
   - Scopes：勾 **openid**、**profile**
   - Add friend option：**On (aggressive)**（開 LIFF 時順便加 bot 好友）
   - 建好後複製 **LIFF ID**（格式 `1234567890-AbCdEfGh`）→ `LIFF_ID=`
4. LINE Login channel 的 **Linked OA**（Basic settings 下方）選 A2 那個官方帳號 → 這樣 LIFF 內的 userId 與 bot 收到的 userId 一致。

### A4. `.env` 收尾
```
LINE_MODE=real
LINE_CHANNEL_SECRET=<A2>
LINE_CHANNEL_ACCESS_TOKEN=<A2>
LINE_LOGIN_CHANNEL_ID=<A3>
LIFF_ID=<A3>
```
（`PUBLIC_BASE_URL` 由 B1 腳本自動填。）

## B. 腳本代勞

前提：API 已在 8140 跑（`.claude/launch.json` 的 `ltc-api` 或 `uv run uvicorn …`），worker 與 STT sidecar 已啟動，前端已 `npm run build`（API 會直接提供 `frontend/dist`，手機用同一個網址）。

```powershell
# B1. 開 Quick Tunnel，取得 https://xxxx.trycloudflare.com，並寫入 PUBLIC_BASE_URL
powershell -ExecutionPolicy Bypass -File F:\ltc_care\deploy\start_tunnel.ps1
# → 重啟 api 與 worker（讀取新的 PUBLIC_BASE_URL）

# B2. 前置檢查＋設定 webhook＋請 LINE 平臺打一次測試請求（真實簽章）
cd F:\ltc_care\backend
uv run python scripts/line_preflight.py --set-webhook --test-webhook

# B3. 圖文選單（六格：問 AI／錄音／問題分類／我的案件／使用說明／小照你好）
uv run python scripts/line_rich_menu.py --delete-others
```

B1 每次重跑網址都會變，**要回 Console 把 LIFF Endpoint URL 改成 `<新網址>/liff`**，並重跑 B2。

## C. 手機實測順序（對應驗收 A4／A5／A8）

1. 後台 `<網址>/admin` 用 `admin_happy` 登入 → 帳號與綁定 → 對「示範照服員 A2（未綁定）」產生綁定碼。
2. 手機掃 Messaging API channel 的 QR code 加 bot 好友 → 收到歡迎訊息＋綁定連結 → 開 LIFF → 輸入綁定碼。
3. 聊天室傳「小照你好」→ 應回打招呼與三個連結；傳文字問題 → 回答附出處＋三顆快速回覆按鈕。
4. 聊天室長按麥克風傳語音「小照你好，照護紀錄要保存多久」→ 先回「已收到語音」→ 幾秒後推播轉錄結果 → 按「用這段提問」。
5. 回答按「播放語音」→ LIFF 內 `<audio>` 播放；聊天室的「播放語音」快速回覆 → 應收到 LINE 音訊訊息（需 HTTPS，Quick Tunnel 符合）。
6. LIFF「錄音」頁：勾同意 → 開始錄音 → 停止 → 自動上傳 → 確認頁標角色。**iOS 與 Android 各測一次並截圖**：能錄、不能錄（顯示替代入口）、格式（頁面會顯示 `audio/webm` 或 `audio/mp4`）。
7. 免手模式：說「小照你好，幫住民洗澡水溫要幾度」。記錄是否觸發、是否誤觸發。
8. 後台回覆案件 → 手機收到推播（案號＋連結）→ LIFF 我的案件看到回覆。

把每步結果（成功／失敗＋截圖＋機型與 LINE 版本）記到 `docs/progress.md` 的「未驗證」表，這樣才算把「模擬」標籤拿掉。

# 智慧眼鏡／Android App 串接指南（2026-11-21）

給 Android 開發端直接參考的 API 規格、連線方式與 Kotlin 呼叫範例。
**不改動任何既有 LIFF／LINE webhook／`/qa/ask` 原本回應格式**——本文件只是把現有 API
整理成手機 App 好用的形式，新增的只有一個 query 參數（`format=hud`）。

## 1. 連線方式：Tailscale 受控內網入口（不是公開網址）

後端 API（port `8140`）現在**只對同一個 Tailscale 帳號登入的裝置**開放，走法是
`tailscale serve`（**不是** Funnel，不會曝露到公開網路）：

```
https://stust.tail379935.ts.net:9446/
```

- Android 手機必須先安裝 Tailscale App、用同一個 Tailscale 帳號登入，才能連到這個網址。
- 這個 port（9446）跟現有的 LINE webhook 用的三個公開 Funnel 入口（根網址、`:8443`、
  `:10000`）完全分開，互不影響；也跟其他兩個既有的「僅限內網」入口（`:9443`、`:9444`、
  `:9445`）用同一套模式，只是轉發目標換成 `127.0.0.1:8140`。
- 本機／區域網路直連（`--host 0.0.0.0` + 開防火牆）**沒有採用**：那樣會把 API 曝露在整個
  Wi-Fi 網段，風險比走 Tailscale 高，故不建議。

檢查目前轉發是否還活著（在這台 Windows 主機上執行）：
```powershell
tailscale serve status
```

## 2. 認證：Bearer Token（不是 Cookie，不需要處理 CORS）

```
POST https://stust.tail379935.ts.net:9446/api/auth/login
Content-Type: application/json

{"username": "...", "password": "..."}
```

回應：
```json
{"status": "ok", "session_token": "<token>", "user": {"id": "...", "role": "caregiver", ...}}
```

之後每個請求都帶：
```
Authorization: Bearer <session_token>
```

- 這是後端既有的機制（`backend/app/auth.py::current_user()`），**沒有新增**任何認證邏輯。
- 照服員帳號走 LINE LIFF 登入（`/api/auth/liff`，需要真實 LINE ID token，跟手機上的
  LINE SDK 綁定），不是這裡的帳密登入（`/auth/login` 僅限 supervisor/director/admin 後台角色）。
  Android App 若要用照服員身分，需要整合 LINE Login SDK 取得 `id_token` 再呼叫 `/api/auth/liff`。
- token 過期或無效時，任何端點都回 `401`，`body.detail.code` 會是 `session_expired`／
  `unauthenticated`／`inactive` 之一；App 端看到 401 就導回登入頁即可，不需要自己判斷過期時間。

## 3. 問答（AR 眼鏡 HUD 精簡格式）

```
POST /api/qa/ask?format=hud
Content-Type: application/json
Authorization: Bearer <token>

{"question": "照護紀錄要保存多久？", "client_request_id": "<自訂, 8~64字, 同一次重試要用同一個>"}
```

回應（精簡，专供小螢幕）：
```json
{
  "outcome": "answered",
  "escalation_reason_text": null,
  "hud_summary": "照護紀錄應保存至少七年…",
  "top_citation": {"document_title": "長照機構服務規範", "locator": "第12條"}
}
```

- `outcome`：`"answered"` 或 `"escalated"`，直接拿來當 HUD 燈號（綠/紅）。
- `escalated` 時 `hud_summary`／`top_citation` 一定是 `null`，改看 `escalation_reason_text`
  （例如「已轉交督導確認」），HUD 應顯示「已轉人工」而不是嘗試顯示答案。
- **省略 `format` 參數**（或 `format=full`）會拿到原本完整的 `/qa/ask` 回應（含完整
  `citations` 陣列、`claims`、`case` 等），LIFF／網頁版維持原樣不受影響。

## 4. 語音上傳（STT）

```
POST /api/audio/uploads
Content-Type: multipart/form-data
Authorization: Bearer <token>

file=<wav/音訊檔>
mode=question          # 或 conversation
client_upload_id=<自訂, 8~64字>
consent_confirmed=true
```

回應裡的 `status` 會是處理中/完成狀態；實際轉錄文字要再查詢逐字稿明細端點（見既有
`caregiver_routes.py` 的 transcripts 系列端點，Android 端沿用跟 LIFF 一樣的輪詢方式即可）。

## 5. 緊急通報（SOS）

```
POST /api/jiaan1030/emergencies
Content-Type: application/json
Authorization: Bearer <token>

{"category": "fall", "client_request_id": "<uuid>"}
```
`category` 只能是：`fall`／`violence`／`injury`／`unresponsive`／`traffic`／`self_harm`／`other`。
建立成功會自動觸發既有的 WebPush 推播給督導端（不需要 App 自己做推播邏輯）。

## 6. Kotlin（OkHttp）呼叫範例

```kotlin
val client = OkHttpClient()
val baseUrl = "https://stust.tail379935.ts.net:9446"
val json = "application/json; charset=utf-8".toMediaType()

// 1) 登入
val loginBody = """{"username":"$username","password":"$password"}""".toRequestBody(json)
val loginReq = Request.Builder().url("$baseUrl/api/auth/login").post(loginBody).build()
val sessionToken: String
client.newCall(loginReq).execute().use { resp ->
    if (!resp.isSuccessful) throw IOException("login failed: ${resp.code}")
    val body = JSONObject(resp.body!!.string())
    sessionToken = body.getString("session_token")
}

// 2) HUD 問答
val askBody = """{"question":"$question","client_request_id":"${UUID.randomUUID()}"}""".toRequestBody(json)
val askReq = Request.Builder()
    .url("$baseUrl/api/qa/ask?format=hud")
    .addHeader("Authorization", "Bearer $sessionToken")
    .post(askBody)
    .build()
client.newCall(askReq).execute().use { resp ->
    if (resp.code == 401) {
        // token 過期/無效：導回登入頁，不要自己重試猜測原因
        return
    }
    val hud = JSONObject(resp.body!!.string())
    val outcome = hud.getString("outcome")              // "answered" / "escalated"
    val summary = hud.optString("hud_summary", null)    // HUD 顯示用一句話
    val topCitation = hud.optJSONObject("top_citation")  // 可能是 null
}
```

## 7. 本機端到端驗證腳本

`backend/scripts/test_wearable_api_flow.py` 會依序模擬：登入 → HUD 問答 → 確認原格式
`/qa/ask` 不受影響 → STT 上傳（靜音測試音檔） → 建立 SOS 通報並立刻自行取消（不留下未
結案通報） → 用無效 token 確認回 401。帳密一律用環境變數，不寫進腳本：

```powershell
$env:WEARABLE_TEST_USERNAME = "<現有帳號>"
$env:WEARABLE_TEST_PASSWORD = "<密碼>"
$env:WEARABLE_TEST_BASE_URL = "http://127.0.0.1:8140"   # 或換成上面的 Tailscale 網址
backend\.venv\Scripts\python.exe backend\scripts\test_wearable_api_flow.py
```

> 注意：腳本會建立一筆真的 SOS 通報再立刻取消，取消前的短暫時間窗內，正式環境既有的
> WebPush 機制仍可能對已訂閱的督導裝置實際推播一次，請在知情的情況下執行。

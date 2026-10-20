# API 契約（v1）

- Base：`/api`；JSON 以 UTF-8；時間一律 ISO 8601（含時區，預設 `Asia/Taipei`）。
- 身分：`Authorization: Bearer <session_token>`。session token 由後端發給，DB 只存雜湊。
- 錯誤格式：`{"error": {"code": "string", "message": "正體中文訊息", "retryable": bool}}`。
- 冪等：會建立資料的 POST 一律帶 `client_request_id`（UUID）或 `client_upload_id`；同一使用者重送回傳**同一筆**資源（HTTP 200），不重建。
- 授權：每個端點檢查角色＋機構。跨機構存取回 404（不洩漏資源是否存在）並寫稽核 `access_denied`。
- 模式標示：涉及 provider 的回應帶 `modes`，例如 `{"llm": "ollama", "stt": "faster_whisper", "line": "mock"}`。

## 1. 身分

| 方法 | 路徑 | 角色 | 請求 | 回應 |
|---|---|---|---|---|
| POST | `/auth/liff` | 無 | `{id_token}` | `{status:"ok", session_token, user}` 或 `{status:"needs_binding"}` |
| POST | `/auth/liff/bind` | 無 | `{id_token, binding_code}` | `{status:"ok", session_token, user}`；綁定碼一次性、有效期 7 天 |
| POST | `/auth/dev-login` | 無（**僅 `LINE_MODE=mock` 且非 production**） | `{username}` | 同上；回應帶 `dev: true` |
| POST | `/auth/login` | 無 | `{username, password}` | 督導／管理員後台登入 |
| POST | `/auth/logout` | 任一 | — | 204 |
| GET | `/me` | 任一 | — | `{id, display_name, role, org:{id,name,facility_type}}` |
| GET | `/config/public` | 無 | — | `{line_mode, liff_id, modes, limits:{question_max_sec, conversation_max_sec, max_upload_mb}, consent_text, qa_policy_version}` |

## 2. 問答

`POST /qa/ask`（caregiver／supervisor）

```json
{"question": "家屬要我幫忙代購成藥可以嗎？", "source": "text|voice|transcript",
 "transcript_id": null, "category_id": null, "client_request_id": "uuid"}
```

回應 `AnswerOut`：

```json
{
  "id": "uuid", "outcome": "answered|escalated|escalation_failed",
  "label": "AI 初步參考",
  "question_masked": "家屬要我幫忙代購成藥可以嗎？",
  "answer_text": "…", "claims": [{"text": "…", "citation_ids": ["c1"]}],
  "citations": [{"id": "c1", "chunk_id": "uuid", "document_title": "…", "doc_type": "regulation|internal_rule|sop",
                 "locator": "第 5 條｜第 3 頁", "version_label": "v2", "effective_from": "2026-01-01",
                 "effective_to": null, "source_url": "/api/sources/chunks/{chunk_id}", "excerpt": "…"}],
  "escalation_reason": null,
  "case": {"id": "uuid", "number": "C-20260911-0001", "status": "pending"},
  "case_error": null,
  "modes": {"llm": "ollama", "embedding": "hash"},
  "qa_policy_version": "2026-09-11.1"
}
```

- `outcome = escalated` 時 `case` 必有值；`escalation_failed` 時 `case = null`、`case_error` 說明原因，前端**不得**顯示「已送交」。
- `citations[].source_url` 由後端依檢索 metadata 產生，LLM 不產 URL。
- 不回傳相似度、信心分數或「正確率」。

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/qa/history` | 自己的問答列表 |
| GET | `/qa/{id}` | 單筆（本人或同機構督導） |
| POST | `/qa/{id}/escalate` | 手動「送交督導確認」`{note, client_request_id}` → `{case}`；失敗回 5xx＋`retryable` |
| POST | `/qa/{id}/retry-escalation` | `escalation_failed` 時重試建案（冪等） |
| POST | `/qa/{id}/feedback` | `{kind:"wrong"|"helpful", reason}` |
| POST | `/qa/{id}/tts` | 建 TTS 工作（冪等：同一回答一筆）→ `{status}` |
| GET | `/qa/{id}/tts` | `{status:"queued|running|ready|failed", audio_url?, error?}`；`audio_url` 為限時簽章 |
| GET | `/media/tts/{token}` | 播放音訊（簽章＋到期檢查，無需 Bearer，可給 LINE 用） |

## 3. 音訊與轉錄

`POST /audio/uploads`（multipart）：`file`、`mode = question|conversation`、`client_upload_id`、`consent_confirmed`（conversation 必須為 true）、`client_mime`。

- 伺服器以 ffprobe **實際解碼**驗證格式與長度，不看副檔名；超限回 413／422。
- 回應 `{transcript_id, status:"queued"}`；同 `client_upload_id` 重送回同一筆。

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/transcripts/{id}` | `{status, mode, segments:[{idx,start_ms,end_ms,speaker,text,uncertain}], speakers, roles, expires_at, error}`；`draft` 狀態的 `text` 為未遮罩草稿（僅本人可讀） |
| POST | `/transcripts/{id}/confirm` | `{segments:[{idx,text,speaker}], roles:{"speaker_1":"caregiver|resident|family|staff|unknown"}, selected_idx:[…], summary}` → 保存遮罩版＋修訂軌跡、刪未遮罩原文 |
| POST | `/transcripts/{id}/retry` | 失敗重試；音訊已過期回 410 `audio_expired`：「音訊已依規定清除，請重新錄製」 |
| DELETE | `/transcripts/{id}` | 取消並立即清除音訊與草稿 |

## 4. 分類與案件（照服員端）

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/categories` | 啟用中的分類與常見問題模板（依機構） |
| POST | `/cases` | `{category_id, template_id?, text, transcript_id?, answer_id?, client_request_id}` → `{case}`；分派到分類預設督導 |
| GET | `/cases/mine` | 我的案件（含狀態、最後回覆時間） |
| GET | `/cases/{id}` | 案件詳情＋訊息（本人或同機構督導） |
| POST | `/cases/{id}/messages` | 照服員補充說明 |

## 5. 知識庫（照服員可見部分）

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/documents/coverage` | 現行涵蓋文件、版本、生效日、知識庫更新時間 |
| GET | `/sources/chunks/{chunk_id}` | 出處原文入口：切塊全文＋文件／版本 metadata（授權＋稽核） |
| GET | `/sources/versions/{id}/file` | 原始檔下載（授權＋稽核） |

## 6. 督導／管理員後台（`/admin/*`）

| 方法 | 路徑 | 角色 | 說明 |
|---|---|---|---|
| GET | `/admin/cases` | sup | 篩選 `status, category_id, assignee_id, q` |
| POST | `/admin/cases/{id}/assign` | sup | `{assignee_id}` |
| POST | `/admin/cases/{id}/take` | sup | 接手 |
| POST | `/admin/cases/{id}/reply` | sup | `{text, client_request_id}` → `{message, notification:{status}}`，回覆與通知工作同一交易 |
| POST | `/admin/cases/{id}/close` | sup | `{reason}` |
| GET | `/admin/notifications` | sup | 通知工作與結果 |
| POST | `/admin/notifications/{id}/retry` | sup | 重送（沿用同一 retry key） |
| GET/POST | `/admin/documents` | sup | 列表／建立文件（`title, doc_type, scope:"org|shared", facility_types[]`）；shared 限 admin |
| POST | `/admin/documents/{id}/versions` | sup | multipart：`file, version_label, effective_from?, effective_to?, source?, source_url?` |
| GET | `/admin/versions/{id}` | sup | 預覽切塊、待補欄位、解析警告 |
| PATCH | `/admin/versions/{id}` | sup | 補中繼資料 |
| POST | `/admin/versions/{id}/publish` | sup | 待補欄位未清空回 422 |
| POST | `/admin/versions/{id}/deactivate` | sup | 停用 |
| GET/POST/PUT | `/admin/categories`、`/admin/categories/{id}` | admin | 分類、模板、預設督導 |
| GET | `/admin/feedback` | sup | 回答錯誤標記 |
| GET | `/admin/metrics?from&to` | sup | 各指標附 `numerator`、`denominator`、定義文字 |
| GET | `/admin/audit` | admin | 稽核紀錄 |
| GET | `/admin/users` | supervisor / admin | 同機構帳號及啟用／LINE 綁定狀態；預設排除已刪帳號，`include_deleted=true` 可唯讀查看，含 `is_deleted`、`original_username`。不變更操作權限 |
| POST | `/admin/users` | admin | 新增同機構 caregiver / supervisor / admin |
| POST | `/admin/users/{id}/binding-code` | supervisor / admin | 僅同機構啟用中的 caregiver；7 天一次性綁定碼 |
| PATCH | `/admin/users/{id}/active` | admin | `{is_active: boolean}`；停用撤銷所有登入及未使用綁定碼，保留歷史資料 |
| DELETE | `/admin/users/{id}` | admin | 同機構 soft delete，不可刪自己；保留 UUID/原顯示名稱/歷史、釋放 username、撤銷綁定與登入，不可重新啟用 |
| DELETE | `/admin/users/{id}/line-binding` | supervisor / admin | 督導僅限同機構 caregiver；admin 限同機構。解除綁定、撤銷 LINE 登入及未使用綁定碼，保留帳號與歷史 |

## 7. LINE

| 方法 | 路徑 | 說明 |
|---|---|---|
| POST | `/line/webhook` | 驗簽失敗 401；成功寫事件＋排工作後回 200 |
| POST | `/dev/line/simulate` | **僅 mock 模式**：組事件、用測試 secret 簽章後打 webhook（`kind: text|audio|follow|unfollow|postback`） |
| GET | `/dev/line/outbox` | **僅 mock 模式**：模擬的 reply／push 紀錄 |

## 8. 健康檢查

`GET /healthz` → `{db:"ok", modes:{…}, worker_heartbeat_age_sec}`

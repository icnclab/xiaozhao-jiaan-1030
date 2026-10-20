# 進度紀錄（中斷後由此續作）

> 專案位置：`F:\ltc_care`（本機 git repo，未推遠端）。資料目錄與帳號清單：`F:\appdata\ltc_care\`。
> 執行中的程序：API（`.claude/launch.json` 的 `ltc-api`，port 8140，`--reload`）、worker（`python -m app.worker`）、STT sidecar（port 8147，`medium`）、Vite（5173）、Ollama（11434）、PostgreSQL（WSL Docker，55432）。

## 目前狀態摘要（2026-09-11）

| 階段 | 狀態 |
|---|---|
| 一：檢查環境、需求對照、架構／資料流／狀態圖、API 契約、驗收清單 | ✅ |
| 二：文字提問→真實文件檢索→帶引用回答→無依據轉督導→督導回覆→照服員看見回覆 | ✅ 瀏覽器實跑驗證（截圖已回看） |
| 三：語音收音、STT、轉錄確認、角色標註、分類回報、TTS | ✅ 後端與 LIFF 完成；瀏覽器無麥克風，錄音頁只驗到「拒絕權限→替代入口」；LINE 語音路徑以真實 STT sidecar 端到端驗證 |
| 四：版本管理、授權隔離、重試、清理、稽核、評測 | ✅ 96 項 pytest 全綠；25 題初測（extractive 25/25；ollama 見 eval-results.md） |
| 追加：喚醒詞「小照你好」 | ✅ 後端稱呼層＋LIFF 免手模式（Web Speech API；實機未驗證） |

## 已完成項（依提示語需求）

- **需求與設計文件**：`docs/requirements.md`（新增／沿用／暫緩對照＋假設）、`architecture.md`（元件圖、問答 StateGraph、案件／轉錄／文件狀態機、模型取捨）、`data-flow.md`（LINE 與瀏覽器語音服務的第三方邊界，不沿用「資料不出境」）、`api-contract.md`、`acceptance.md`（13 項驗收＋評測與效能量測規格＋未驗證清單）、`deployment.md`。
- **後端**（FastAPI＋SQLAlchemy＋Alembic＋LangGraph）：
  - 資料模型 25 張表（機構、使用者、LINE 綁定、綁定碼、session、分類與模板、文件／版本／切塊、問答／引用、轉錄／片段／修訂、案件／歷程／訊息、通知工作、回饋、稽核、LINE 事件、模擬信箱、工作佇列、TTS 資產、自訂遮罩詞、worker 心跳）；migration `0001`（含 pgvector、案號序列、稽核與案件歷程 append-only 觸發器）。
  - 問答流程 `services/qa_graph.py`：deidentify → screen_risk → retrieve（IDF 加權雙連詞全文＋雜湊向量混合，限現行版本、機構、機構類型）→ generate（Ollama JSON schema／摘錄模式／mock）→ verify（引用存在、字面支持度、輸出風險、跨文件數值衝突）→ answer／escalate（建案失敗＝`escalation_failed`，不假裝已轉交）。門檻版本 `2026-09-11.2`。
  - 去識別化 `services/deid.py`（姓＋稱謂、角色詞＋姓名、房床號、電話、證號、日期、機構自訂 HMAC 詞）＋18 項規則測試。
  - 喚醒詞 `services/wake.py`（LINE 文字／語音、LIFF 三入口共用；同音 小昭／小趙；純打招呼回提示）。
  - LINE：原始 body HMAC 驗簽、`webhookEventId` 去重、`isRedelivery` 計數、reply token 逾時改 push、`X-Line-Retry-Key`、429／400 分類、unfollow 標記封鎖、外部 `contentProvider` 不下載（SSRF）、mock client 與模擬器端點（僅 mock＋非 production）。
  - 語音：ffprobe 實際解碼驗證、長度與大小上限、冪等上傳、STT sidecar adapter、原音 STT 後即刪、失敗重試、音訊到期→要求重錄、未遮罩草稿 Fernet 加密＋24h 到期、確認後只存遮罩版與修訂軌跡、說話者預設未辨識。
  - 案件：狀態機（pending→in_progress→replied→closed）、分類預設督導路由、回覆＋歷程＋通知工作同一交易、通知狀態 queued／sending／accepted／failed／skipped（accepted≠送達）。
  - 文件：PDF／DOCX／文字解析（檔頭判斷）、法規按條／內規按段切塊、待補欄位阻擋發布、現行版本查詢時計算、停用、歷史引用回到當時版本。
  - 治理指標（每項附分子／分母／定義）、回饋、稽核、帳號與綁定碼、保留清理（音訊、草稿、TTS、事件內容、session、孤兒檔）。
  - 日誌遮罩過濾器（Bearer／token／媒體簽章 URL）；稽核 meta 禁止敏感鍵。
- **前端**（React＋TS＋Vite）：`/liff`（首頁、問 AI＋語音提問＋免手模式、回答與出處卡＋TTS＋送交督導＋回答有誤、錄音／談話紀錄、轉錄確認與角色標註、分類回報三步、我的案件、使用說明與涵蓋範圍、綁定）；`/admin`（登入、案件列表／詳情／接手／改派／回覆／結案／通知重送、文件與版本管理、分類設定、回饋、指標、帳號與綁定碼、LINE 模擬器）。模式標示列、模擬模式警示。
- **STT sidecar** `services/stt_sidecar/server.py`（faster-whisper，CUDA，OpenCC 正體，uncertain 標記）。
- **合成資料**：`demo/documents/`（8 份，含版本差異、衝突、注入、居家、他機構）、`scripts/seed_demo.py`、`scripts/make_demo_docs.py`；評測 `demo/eval/questions.jsonl`（25 題）＋`scripts/eval_run.py`；`demo/DEMO_SCRIPT.md`；`scripts/demo_line_voice.py`（LINE 語音端到端）。
- **Docker**：`docker-compose.yml`（db 開發；`--profile app` 全容器）、`backend/Dockerfile`、`frontend/Dockerfile`＋`nginx.conf`。相依鎖定：`backend/uv.lock`、`frontend/package-lock.json`。

## 執行指令與測試結果

| 項目 | 指令 | 結果 |
|---|---|---|
| 後端測試 | `cd backend && uv run pytest` | **96 passed**（deid 18、qa_flow 11、injection 6、line_webhook 9、transcripts 8、cases 6、tts 2、authz 10、documents 7、retention 5、wake 14） |
| 初測（摘錄模式） | `uv run python scripts/eval_run.py --llm extractive` | **25/25**；出口正確 25/25；引用禁止文件 0 |
| 初測（Ollama gemma4:e4b） | `uv run python scripts/eval_run.py --llm ollama` | **25/25**（政策 2026-09-11.2；延遲見 `docs/eval-results.md`）；早先曾出現 llm_error 逾時，原因見下 |
| 前端建置 | `cd frontend && npm run build` | tsc＋vite 通過 |
| 瀏覽器實跑 | LIFF 手機尺寸＋後台 | 文字提問→出處卡→查看原文→TTS 播放（audio/mp4 199 KB，簽章 URL 200）→ 後台接手回覆 → 通知 accepted → LIFF 我的案件看到回覆；分類回報頁、案件列表、文件頁、指標頁、模擬器頁皆渲染 |
| LINE 語音端到端 | `uv run python scripts/demo_line_voice.py` | SAPI 合成「小照你好，照護紀錄要保存多久」→ 模擬 webhook → 真實 STT（medium）→ 推播轉錄（約 4.6 s，含上傳與轉檔）→ postback 提問 → 回答推播「照顧紀錄應至少保存七年（出處 1：營運規範第 7 條第 2 版）」。第一次跑 STT 聽成「小趙你好,照護記錄要儲存多久?」而轉督導；補喚醒詞同音、同義詞與 sidecar initial_prompt 後可答 |

**效能觀察（單機、併發 1、樣本小，不宣稱 P95）**：文字問答經生成節點 1.1–2.7 s（Ollama 已預熱、GPU 未爭用）；規則直接轉人工 < 0.1 s；STT medium 對 3 秒語音約 1–2 s。RTX 3080 10 GB 同時載入 whisper large-v3 與 gemma4 時 LLM 生成逾時（60 s），改 `medium` 後正常。

## 修改紀錄（重要決策）

- 埠位改 8140／8141／8147（8040 已被本機 ipas_learn 占用，見 tools/fix_winnat_ports.ps1）。
- 檢索 coverage 改 IDF 加權；`min_top_coverage` 0.30→0.35（合成評測：可答題最低 0.38，無依據誤中 0.32；邊界薄，真實語料須重校）。
- 摘錄模式第二句須達第一句相關度 60%，避免附上不相干條文。
- Ollama：`num_predict=400`（避免失控生成拖垮後續請求）、`num_ctx=6144`、啟動預熱同 ctx、`keep_alive=30m`。
- 喚醒詞比對只在比對時 NFKC，回傳原文（保留全形問號）；同長度喚醒詞維持設定順序。
- 工作 `run_after` 改用資料庫時間（避免主機／容器時鐘偏差）。
- `.env` 不用行內註解（dotenv 會把空值後的註解當成值）。
- 同義詞正規化加入 記錄→紀錄、儲存→保存（實測 whisper 輸出）；喚醒詞加入「小趙」；sidecar `initial_prompt` 加入喚醒詞寫法。

## 待解問題／已知限制

1. **真實 LINE 未串接**：無 channel 憑證；模擬器驗證的是本系統這一側（驗簽、去重、處理、reply／push 內容）。
2. **LIFF 錄音與免手模式未在 iOS／Android LINE 內建瀏覽器實測**；Browser pane 無麥克風，只驗到權限拒絕→替代入口。
3. **中華電信 STT／TTS、hicloud 未串接**（adapter 保留，呼叫即報錯）。
4. **Docker `--profile app` 未實際建置映像**（本機 Docker 只在 WSL；compose 檔與 Dockerfile 已寫）。
5. **引用支持度未人工標註**：`docs/eval-citation-review.csv` 待團隊填最後一欄。
6. 說話者分段只有 `none`；多人重疊語音、臺語、口音、噪音未測。
7. 去識別化為規則式；無稱謂的單獨人名會漏遮（已在說明頁提醒用代稱）。
8. TTS 只在 Windows 主機（SAPI）；容器內退 mock。
9. 評測門檻以合成資料校準，真實法規語料入庫後須重跑並版本化。
10. 主機 GPU 10 GB：LLM 與 STT 共存時 STT 用 `medium`；`large-v3` 只在單獨跑 STT 時使用。

## 真實 LINE 串接準備（2026-09-11 晚，步驟 1 啟動）

- 本機 cloudflared **Named Tunnel 已割接到部署機（服務 Stopped/Disabled）**，本機實測改用 **Quick Tunnel**：`deploy/start_tunnel.ps1` → `https://xxxx.trycloudflare.com` → 8140，並自動寫入 `PUBLIC_BASE_URL`。
- API 現在**直接提供 `frontend/dist`**（SPA fallback，`/api` 之外的路徑回 index.html），手機用同一個 HTTPS 網址開 LIFF／後台／API；記得改前端後 `npm run build`。踩坑：catch-all 路由必須註冊在所有 `/api` 路由之後，否則 `/api/healthz` 被蓋成 404。
- `scripts/line_preflight.py`：驗 `.env`、`GET /v2/bot/info`（token）、chatMode、`--set-webhook`／`--test-webhook`（LINE 平臺真實簽章打本機）、推播額度。全程不印密鑰。
- `scripts/line_rich_menu.py`：六格圖文選單（Pillow 產圖、uri→LIFF 或 message 關鍵字）。
- 你要做的事寫在 `docs/line-setup-checklist.md` A 段（建 provider＋兩個 channel、貼 secret/token/ID 進 `.env`）；C 段是手機實測順序與要記錄的證據。
- uvicorn `--reload` 在此機偵測到變更後未完成重啟（log 只有 Reloading… 無新 startup），改檔後直接重啟 `ltc-api`。
- **2026-09-11 22:50 真實 LINE 已接通（本機側）**：channel 建好（LIFF `2011564212-Udqt7Tbh`、bot `@490fhnap`），`LINE_MODE=real`；Quick Tunnel `https://hour-elsewhere-flashing-affects.trycloudflare.com`；`--set-webhook` 200；**LINE 平臺以真實簽章打 `/api/line/webhook` 回 200（簽章驗證通過）**；圖文選單已建並設為預設。待本人：Console 開「Use webhook」、LIFF Endpoint 改成 tunnel `/liff`、Linked OA、手機實測（清單 C 段）。
- 兩個坑：①cloudflared 會自動載入 `~/.cloudflared/config.yml`（舊 Named Tunnel 的 ingress，catch-all 404），Quick Tunnel 必須 `--config` 指到獨立最小設定檔，否則公網全 404 且不到 origin；②PowerShell `[IO.File]::ReadAllText` 讀 `.env` 曾回空字串並把檔案清空（密鑰全失、DB 密碼與加密金鑰重生、重 seed），現在 `.env` 一律走 `scripts/env_set.py`（內容過短拒改），`.env.bak` 機制與 `reset_db_password.py` 已備。

## 手機實機驗證（2026-09-11 23:3x–23:4x，Android 手機、LINE 內建瀏覽器，真實 LINE channel）

本人回報清單 C 段 6 步全部成功；伺服器端證據（稽核與資料表，無個資）：

| 驗收 | 證據 | 結論 |
|---|---|---|
| 加好友→歡迎訊息→綁定 | `line.webhook` 事件 23:34 進站；`auth.bind` 23:36 成功（cg_happy_2 綁定，LINE userId 33 字元） | ✅ A 段帳號綁定 |
| A5 LIFF 錄音（Android） | 兩筆 `channel=liff, mode=question`，實際解碼 `matroska,webm/opus`（前端宣告 `audio/webm;codecs=opus`），9.2 s／9.9 s、108–130 KB；STT faster-whisper medium 0.96 s；**原音 STT 後已刪除** | ✅ Android；⬜ iOS 未測 |
| 語音提問→回答 | 兩筆 `source=voice` 皆 `answered`，喚醒詞辨識 `wake=True`；graph 9.6 s（第一題、模型冷）→ 2.4 s | ✅ |
| A4 LINE 原生語音 | 本人回報步驟 5 成功（收到「已收到語音」→轉錄推播→用這段提問） | ✅（Android） |
| 聊天文字＋圖文選單 | 23:41–23:42 兩筆 webhook 事件 `new=1`，無重複 | ✅ |

尚未在實機驗證：iOS LINE 內建瀏覽器錄音；手機端 TTS 播放（LIFF `<audio>` 與 LINE 音訊訊息）；督導回覆後的推播到達手機；免手模式（Web Speech API）在 LINE 內建瀏覽器的觸發率。Quick Tunnel 網址為臨時，重啟即失效（需重跑 `deploy/start_tunnel.ps1`、`--set-webhook`、改 LIFF Endpoint）。


## 2026-09-12 截圖、部署與安裝包

- **截圖**：`tools/shot_prep.py`（打 mock 實例佈置問答／衝突案件／談話轉錄／督導回覆）＋`tools/shots.js`（puppeteer，借 mermaid-cli 的瀏覽器）→ 24 張 PNG 到 `規劃書v4_圖/screens/`；截圖用的 mock 實例以環境變數覆蓋 `.env`（`LINE_MODE=mock`、埠 8150），與真實模式互不干擾。構想書 v4 新增 5.5（LIFF 四組）、5.6（後台六張）、5.7（手機 LINE 實機圖，讀 `screens_line/`＋`captions.json`，有檔才出現）。
- **安裝包**：`deploy/install/`（`install.ps1`／`start.ps1`／`stop.ps1`／`status.ps1`／`install_stt.ps1`／`build_package.ps1`／`README_安裝.md`，由 `tools/gen_installer_files.py` 產生，含 UTF-8 BOM）。`build_package.ps1` 產出 `ltc_care_installer_<日期>.zip`（前端 dist＋cp311/cp312 離線 wheels 82 顆＋ffmpeg/ffprobe＋程式碼；220 MB）。新增設定 `FFMPEG_DIR`（內建 ffmpeg 免改 PATH）。安裝包副本：`D:\Dropbox.學生競賽\羅心妤團隊_長照專題\安裝包\`。
- **部署機（deploy-24h／Tsai）**：RTX 5080 16 GB、Python 3.11.9、Ollama 已有 `gemma4:e4b`、WSL `Ubuntu-22.04-moodle` 內 docker。`deploy/deploy24h_setup.ps1`：解壓 → `install.ps1 -WithStt` → 還原家中機 DB dump＋文件原檔（保留已綁定的 LINE 帳號與學生綁定碼）→ 複製 LINE 憑證與金鑰 → `APP_ENV=production`、`PUBLIC_BASE_URL=https://ltc.icnclab.net`、LLM ollama、STT large-v3(cuda) → 排程 `LTC Serve`（登入自啟）＋WMI 立即啟動 → SYSTEM 端 cloudflared config 加 `ltc.icnclab.net → 8140` 並重啟。DNS CNAME 已由家中機 `cloudflared tunnel route dns ai-quiz ltc.icnclab.net` 建立。踩坑：★ssh 過去跑的 .ps1 含中文必須 UTF-8 BOM，否則 PS 5.1 解析錯誤（整支腳本不執行）。

## 下一步

1. 團隊取得 LINE channel（同 provider 的 Messaging API＋Login）→ `LINE_MODE=real` 實機驗證 webhook、LIFF、錄音、TTS 音訊訊息（需 HTTPS 公網）。
2. 真實法規（全國法規資料庫）與機構內規入庫（督導後台上傳、補生效日與來源），重跑評測並人工抽查引用。
3. 中華電信 STT／TTS 規格到手後實作 `ChtStt`／`ChtTts`。
4. 機構正式錄音同意流程、資安審查（資料流圖已備）。
5. Compose 映像在 WSL 內建置驗證；正式主機部署（`APP_ENV=production`）。

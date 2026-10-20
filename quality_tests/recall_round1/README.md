# 居家長照召回率第一輪：準備完成，正式基準尚不可計分

本次只讀取已存在的檔案；沒有連線資料庫、執行搜尋、呼叫模型或重啟服務。
不能把這份歷史快照盤點說成「目前程式的真實搜尋基準」。

## 論文全文核對與方法

頁碼採 PDF 從第一頁起算；歷史檔案論文另列印刷頁碼。

| 論文 | 實際頁碼 | 本輪採用的方法／限制 |
|---|---|---|
| [RAGChecker 全文](https://arxiv.org/pdf/2408.08067) | PDF 4–5頁，§3.1–3.3.2 | 將標準答案拆成必要事實，人工判斷快照是否支持每個事實；不是以字面關鍵字命中代替語意支持。 |
| 同上 | PDF 6–7頁，§4.1–4.2 | 比較檢索與生成，並用人工評估檢驗評估器；本輪不沿用其模型評審分數。 |
| 同上 | PDF 22頁，Appendix H | 英文文字資料集、評估器與檢索指標都有侷限；不能直接推論繁體中文居家長照表現。 |
| [A Preliminary Study of RAG for Taiwanese Historical Archives 全文](https://aclanthology.org/2025.rocling-main.6.pdf) | PDF 2–3頁／印刷46–47頁，§3 | 問題與相關段落對齊，保留題目及文件中繼資料。 |
| 同上 | PDF 4–5頁／印刷48–49頁，§4.4、§5 | Recall@k以相關段落為單位，與本輪必要事實召回率不同；分開檢索及答案品質。 |
| 同上 | PDF 7–8頁／印刷51–52頁，§6.3、§7 | 不同題型與中繼資料策略結果不同；歷史文本結果不能直接當成長照改善成效。 |

A/B/C 是本專案的分階段離線評估，不宣稱是兩篇論文原有的三個指標。
這輪不修改 Top-K、權重、同義詞、Reranker 或證據門檻。

## 現有工具檢查

- `offline_rag_metrics.py`：原本已有候選、gate及提供者輸入快照，但沒有 Gate Recall；Selected Recall 原本使用提供者輸入。本輪升為 `offline-rag-1.1`，新增 Gate Recall，優先使用真正選入的 `evidence` 快照。
- 舊快照只有已觀察的 `generation_context` 時保留相容讀取；明確存在但缺失的 Selected 不會被其他資料補成有值。
- `run_answer_quality_v1.py`：有不連 DB 的 `--reevaluate`，但 live 分支只檢查資料庫名為 `ltc_clean`；本次不執行 live 分支。
- `evaluate_gold_v1.py`：live 路徑同樣依賴 `ltc_clean`，預設輸出接近 Frozen Gold；本次不執行，也不修改它。
- `quality_trace.py`：保存檢索候選、gate、選入ID及版本資訊；僅有ID不等於保存了完整模型輸入。本輪不修改此正式追蹤程式。
- 離線 observer 現在可記錄提供者收到的問題／證據，並在真正發出 Ollama HTTP post 時記錄原始 JSON，包括 messages；不從答案反推 prompt。尚未執行真實模型捕捉。空請求清單表示 observer 未觀察到請求；舊快照缺欄位則為未知。

## 資料與審核狀態

- `dataset.json`：18筆既有已審核回饋，加2筆既有校準題（C003、C014），合計20筆，題目逐字保留。沒有捏造訪談，也沒有自行創造新題目。
- 其中6題預期知識查詢，13題安全攔截，1題澄清。這是20題候選及對照組，尚不是20題合格召回率題庫。
- 原始 Gold 的審核狀態保存在 `prior_review`，但不能自動當作本輪「原子事實＋A/B/C蘊含＋版本／居家適用性」審核。新審核通過數為0。
- `required_facts_draft_verbatim` 是逐字引用既有標準答案的待審草稿，不是已完成的原子事實。正式 `required_facts` 目前留空。
- 每題保留來源檔案、原ID、來源SHA256、既有正確文件／定位及可得版本；缺少正確版本、原始文件或適用性確認時保留缺值，禁止計分。
- 既有回饋含系統安全政策依據；這些不能冒充知識庫條文，也不能放入搜尋召回率分母。
- `observations.json` 只保存歷史候選及gate等已觀察資料。選入ID不會被當成完整選入文字，更不會當成真正模型輸入。
- `annotations.json` 初始為空白人工標註表；沒有自動將答案或關鍵字標成命中。

歷史觀察：8題有搜尋紀錄；11題有風險攔截且沒有搜尋紀錄；1題無法確認是否搜尋。A候選及B gate各8題有快照，C完整選入文字及真正模型請求均未保存。以上是觀察數，不是召回率。

## 環境檢查

唯讀設定盤點發現目前應用資料庫名是 `ltc_clean`，設定另有 `ltc_test`。
不同名稱不代表已確認安全隔離；尚未驗證容器、volume、資料來源及測試清除範圍。
資料庫連線次數：0。本輪使用既有本機歷史快照，不對 production DB執行問答或評估。

## 評分規則

每階段召回率＝該階段支持的必要事實數／已審核必要事實總數。

- A Candidate：搜尋輸出候選全文。
- B Gate：通過資格檢查的候選全文。
- C Selected：最後選入的證據全文；與真正模型請求另存，不能混為一談。
- 人工標註必須綁定 `case_sha256` 及 `snapshot_sha256`，且方法為 `human_review`。
- 每個正式事實要有文件、版本及頁碼／條號；案件還須填審核人、審核時間與 `home_care_confirmed`。
- 沒搜尋、沒標註、快照缺失或雜湊不符時是 `null`，不是0%。
- 報告逐題分別保留A/B/C結果；總表使用三階段共同可評題目，避免分母不同造成假比較。
- 逐事實可區分「候選未涵蓋」「gate排除」「選擇遺漏」；安全未搜尋及版本／機構不適用另列。沒有足夠證據時不定位責任階段。
- 這些是報告觀察欄位，不修改專案 Failure Type，也不啟用 Failure Diagnosis。

## 本輪結果

正式結果見 `baseline_report.json`。A、B、C全部為 null，正式共同可評題目為0。
原因：必要事實／版本及適用性未完成本輪人工審核，完整C快照缺失。
本次沒有呼叫模型；歷史真正模型輸入未知，不以重建提示冒充。
尚無法判斷應先調整搜尋、gate或最後選擇。

最值得先完成的工作：先審核6題既有知識查詢的必要事實與原始文件版本，並準備安全隔離的完整A/B/C快照；不能現在就把歷史失敗歸咎於Top-K。

## 安全重跑

僅重新評分已保存檔案（不搜尋、不連DB）；輸出名稱必須是尚未存在的新檔案：

```powershell
backend\.venv\Scripts\python.exe -B backend/checks/recall_baseline.py --output quality_tests/recall_round1/reviewed_run_001.json
```

只有人工完成審核並填妥綁定雜湊的annotations後，才可能產生正式數字；未補資料重跑仍應為null。

隔離測試（阻擋app/DB模組、網路、子程序及正式設定／資料集讀取）：

```powershell
backend\.venv\Scripts\python.exe -B backend/checks/run_offline_metric_tests.py --suite recall
backend\.venv\Scripts\python.exe -B backend/checks/run_offline_metric_tests.py --suite phase1
```

本輪新增24項通過，既有46項通過，共70/70。沒有執行research suite或pytest fixtures。

準備資料時保存四個來源檔案SHA256，完成後再比對均相同。Frozen Gold v1及正式搜尋、排序、政策、模型、知識庫均未修改。

# 罰款金額證據充分性修正

## 原因與修改

「行政聯繫會議缺席一次要罰多少錢」原先通過檢索門檻，模型卻回答「評鑑當日業務負責人未出席，本項逕評核為 E」。
引用存在且字面支持度高，但內容沒有回答缺席行政聯繫會議的罰款金額。
原驗證檢查引用支持主張，未檢查主張是否包含問題所問事實。

修改前備份三個既有檔案，後綴均為 .bak_20261006_135602_sufficiency。

| 檔案 | 修改 |
|---|---|
| backend/app/services/evidence_sufficiency.py（新增） | 通用辨識罰款、罰鍰、罰金、扣薪與扣款金額問題；檢查同一句有相關主題、處罰與貨幣金額，避免借用其他句子的金額。 |
| backend/app/services/qa_graph.py | 生成前若證據缺少所問金額，直接以 insufficient 轉人工；驗證後若回答未提供引用所支持的金額，也轉人工。原驗證全部保留。 |
| backend/app/services/retrieval.py | 將「行政聯繫會議多久至少要開一次」「督導制度多久至少要開一次聯繫會議」轉換為文件用詞；不寫入答案數字，不要求使用者一定提及居家機構。 |
| backend/app/services/qa_policy.py | 政策版本更新為 2026-10-06.1，便於稽核。所有 retrieval/support 門檻不變，風險規則不變。 |

沒有寫死完整問題，也沒有一律拒答罰款問題：單元測試使用合成規定「行政聯繫會議缺席一次罰款3,000元」，有證據時可通過。
這是罰款／扣款金額的必要事實檢核，並非所有意圖的完整語意判斷。
金額與主題無法明確對應時採保守轉人工；未經測試的新法規仍可能出現誤拒。

## 結果

資料庫 READ ONLY，直接執行完整 graph，不寫問答或通知、不重建知識庫。
測試固定日期 2026-10-06、HAPPY 機構與現行已發布文件。
正式 25 題沿用此前凍結的歷史測試 snapshot。

| 測試 | 結果 |
|---|---|
| 行政聯繫會議缺席一次要罰多少錢 | 轉人工，insufficient；證據未提供所問金額，未進 LLM。 |
| 行政聯繫會議多久至少要開一次 | 回答至少每 3 個月，引用 115 年度居家式機構評鑑基準。 |
| 督導制度多久至少要開一次聯繫會議 | 回答至少每 3 個月，引用同一評鑑基準。 |
| 缺席會議罰款金額／扣薪問法 | 皆轉人工；扣薪變體修改前也會答非所問，修改後修正。 |
| 正式 25 題 | 25/25 回歸通過，出口與引用文件／版本維持一致，五題拒答維持正確拒答。 |
| Q1、Q3 與兩個變體 | 4/4 答案關鍵事實與引用核對通過。 |
| 合計完整 graph | 34/34 通過。 |
| 證據充分性單元測試 | 8/8：金額意圖、頻率不誤判、E 評分不是金額、無關金額、正確金額可答、捏造金額拒絕、高支持度答非所問拒絕。 |
| 既有 Q1/Q3 與 provider 回歸 | 各 5/5 通過；語法編譯通過。 |

正式題中一題回答額外出現文字標記 (E3)，事實內容未變，引用仍正確；其他正式題的 claims 與先前結果相同。
回歸結果不等於所有未知自然語言問題都達相同正確率。

## 速度

不新增 LLM 呼叫。罰款題修改前約 1.88 秒，修改後約 44 ms，因證據不足而提早結束。
正式可答題本次中位數約 1.89 秒，前次約 2.05 秒；未觀察到速度退步，但不同批次負載及快取會影響數值，不能將差異全歸因於此修正。
統計為完整 graph 的伺服器端 wall time，不含前端、API 持久化或網路。

## 重跑與產物

```powershell
# backend 目錄
.venv/Scripts/python.exe scripts/check_sufficiency.py after
.venv/Scripts/python.exe scripts/test_evidence_sufficiency.py
.venv/Scripts/python.exe scripts/test_q1_q3_expansion.py
.venv/Scripts/python.exe scripts/test_answer_speed.py
```

before 結果：evidence_sufficiency_before.json；最終結果：evidence_sufficiency_after.json。
before 模式只比較五個新增邊界題，使用本次備份的 graph/retrieval。
本次未重啟 Backend 或 Worker；常駐服務需重新載入更新後的程式才會生效。

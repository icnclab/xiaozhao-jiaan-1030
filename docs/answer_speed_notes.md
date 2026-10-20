# 回答速度優化與驗證

## 最終修改

- backend/app/providers/llm.py：跨 provider 實例重用 httpx.Client，減少每題重新建立連線及 client 的固定開銷；程序結束時關閉連線。
- 保留 Ollama 原始耗時（奈秒）與輸入/輸出 token 數至 CandidateAnswer.metrics。
- backend/app/services/qa_graph.py：將模型統計存入 checks.llm_metrics，補上 evidence_prepare 毫秒與證據數/字數。
- 模型、temperature、num_ctx、num_predict、JSON schema、SYSTEM_PROMPT、全部證據、召回門檻與驗證規則保持原樣。

修改前備份：

- backend/app/providers/llm.py.bak_20261006_133900_speed
- backend/app/services/qa_graph.py.bak_20261006_133900_speed

## 測試

測試以固定日期 2026-10-06、HAPPY 居家機構、現行知識庫，執行完整 run_graph。
正式 25 題沿用前次從歷史紀錄擷取的固定 snapshot，另含 Q1、Q3 及兩個變體。
資料庫交易 READ ONLY，不新增問答、通知或修改知識庫。

| 指標 | 修改前 | 最終版本 |
|---|---:|---:|
| 29 題出口與既有結果一致 | 29/29 | 29/29 |
| 引用文件＋版本集合一致 | 29/29 | 29/29 |
| 可答題中位數（24 題） | 2.143 秒 | 2.047 秒 |
| 可答題平均 | 2.159 秒 | 2.127 秒 |
| 可答題最大 | 3.375 秒 | 3.488 秒 |

25 題前後測的回答文字、引用代號及支持度完全一致；所有 29 題的證據全文亦完全一致。
五個正式拒答題維持拒答。四個新增可答题的期限/頻率與引用核對通過。
Q1 變體補充說明有模型生成差異，但核心「有效期限屆至前六個月內申請更新」及第 12 條引用正確。
以上為固定測試集回歸結果，不等於任意新問題的正確率保證。

量測為伺服器端完整 graph 的 wall time，不包含 API 寫入、前端、網路或 LINE worker 排程。
每题一次，同一模型依序執行，輸入快取與硬體負載可能影響結果；約 0.10 秒的中位數改善屬小幅改善。
較長評鑑題未達 2 秒。最終模型統計中位數：載入約 3.6 ms、輸入處理約 153 ms、輸出生成約 1390 ms。

額外測試：provider mock HTTP 測試 5/5、Q1/Q3 查詢轉換回歸 5/5、語法編譯通過。
mock HTTP 測試涵蓋引用解析、metrics、壞 JSON 拒絕、連線重用，以及提示詞/schema 與備份一致。

## 試驗取捨

曾試驗優先一句回答的提示詞，但造成異常事件與評鑑題誤拒答、速度也退步，已完全撤回。
answer_speed_after.json 是已撤回試驗的結果，不能當作最終結果。
最終結果：answer_speed_final.json；基線：answer_speed_before.json。

重跑方式（backend 目錄）：

```powershell
.venv/Scripts/python.exe scripts/check_answer_speed.py final
.venv/Scripts/python.exe scripts/test_answer_speed.py
.venv/Scripts/python.exe scripts/test_q1_q3_expansion.py
```

常駐服務須載入更新後的程式才會使用連線重用；本次未重啟服務。

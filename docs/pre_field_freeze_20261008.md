# 場域測試前版本 Freeze 紀錄（2026-10-08）

建立时间（Asia/Taipei）：2026-10-08T11:08:54.438401+08:00；UTC：2026-10-08T03:08:54.438401+00:00。

專案：`C:\aa\ltc_care_installer_20260912\ltc_care`；qa_policy version：`2026-10-08.local-fixes.1`。

此 freeze 是可比對的版本 checkpoint 與實體備份，不是修改檔案權限或部署核准。本輪未改核心、prompt、gold、KB；後續測試应以此 SHA256 baseline 辨識版本。

備份位置：`C:\aa\ltc_care_installer_20260912\ltc_care\backups\pre_field_freeze_20261008_110854`。包含目前核心、相關測試／回歸工具及最新結果；`manifest.json` 列每份實際備份 SHA256。未複製 .env／帳密。較早的 `.bak_local_20261008_103005` 是局部修正前，不代表本次凍結版本。

## 核心檔案 SHA256

| relative path | SHA256 |
|---|---|
| backend/app/services/retrieval.py | `2419df0e32dca259c9780f79a5b06a863b98ae219d2b78bc4d9357c4b8027e96` |
| backend/app/services/retrieval_gate.py | `2b244c2913c72294e8314c1c544f6d08b47fa272f70f32d863339aa202e1eca8` |
| backend/app/services/query_understanding.py | `c4671dc662f4e912f80ae350448bb9f81cdef478a37132e0bf6bb16254ce95c8` |
| backend/app/services/evidence_text.py | `98000cd80b265f28eee3f02e18727550a13d12e6631b4673536477cb33d47fec` |
| backend/app/services/qa_graph.py | `e91f2d2f6f5bbf03a2542a34725f0ca8ade2a7d829868859a51a256aa908dd8b` |
| backend/app/services/qa_policy.py | `bf3a5fe77b70fa85cbb2b8c3e1ac29049a3e85bfad3f00fd0d9fe685e2b53ec5` |
| backend/app/services/qa_service.py | `629e51f6c32793f445d7f16efe71850cc42cba0236c84184594b80f815a3990c` |
| backend/app/services/evidence_sufficiency.py | `fa8403cbb909d054002817f0b5ded3ce275a08a3059db2ecddce27ee60330500` |
| backend/app/services/evidence_selection.py | `8cf0dae7188f1bcb63af86132d0dbc4c3c8d8fa2e8b8dc2e0b15ab4101197ea6` |
| backend/app/services/role_consistency.py | `1c58746ca170754e56a4d2a7a791c543f7bd96dd874539b5f5b498b9dc575632` |

以上 10 項均與最新 regression 的 core_sha256_after 完全相同；分析前後另行比對不變。風險／clarify 相關 qa_policy、qa_graph、query_understanding、qa_service 與 citation／role／選證模組均納入。補充 source／工具／結果備份 hash：

| relative path | SHA256 |
|---|---|
| backend/app/services/text.py | `0247933ac305a775fcf22d31f67159235aede1a084d84ec8bad410c3a2d1c00d` |
| backend/app/providers/llm.py | `a09ab041adfeada84e27b8604d2dd5215b06ae5f3b1b2fd50c661e44b91725e8` |
| docs/regression_local_fixes_20261008.json | `71bb84cd7bc727be416eb736fc305b7059743ba99bd8181a80ed9e63466bd235` |
| docs/regression_local_fixes_20261008.md | `efd6adc1d77653b4a22ea18f78f39ca3b20276e3f404225901281a0b3a9fe172` |
| docs/local_fixes_20261008_tests.xml | `ba515d2f6f0a97a0395ae46ce6b599565e27024ca2045a5ff2c419080d1b14e8` |
| docs/local_fixes_role_replay_20261008.json | `62e5d788ffa35fcc79bc8e13013b55509b2040fd334667b5ec64911f27bb13c0` |

## Tests（既有執行結果，非本輪重新執行）

```json
{
  "name": "pytest",
  "errors": "0",
  "failures": "0",
  "skipped": "0",
  "tests": "148",
  "time": "63.732",
  "timestamp": "2026-10-08T10:46:10.349652+08:00",
  "hostname": "STUST"
}
```

JUnit：`docs/local_fixes_20261008_tests.xml`；148/148 passed，0 failures、0 errors、0 skipped，63.732 秒。此次只分析與紀錄，沒有重跑 suite，也沒有宣稱新增驗證。

## 最新 regression baseline

來源：`docs/regression_local_fixes_20261008.json`；SHA256：`71bb84cd7bc727be416eb736fc305b7059743ba99bd8181a80ed9e63466bd235`。

執行 UTC：2026-10-08T02:47:58.762920+00:00 ～ 2026-10-08T02:49:16.485041+00:00；40 題 × 1 輪，與較早 40 × 2 輪分開。

```json
{
  "outcome_accuracy": {
    "numerator": 40,
    "denominator": 40,
    "rate": 1.0
  },
  "answerable_correct_answer_rate": {
    "numerator": 21,
    "denominator": 24,
    "rate": 0.875
  },
  "false_refusals": 0,
  "unsafe_answers": 0,
  "clarify_accuracy": {
    "numerator": 4,
    "denominator": 4,
    "rate": 1.0
  },
  "no_evidence_accuracy": {
    "numerator": 4,
    "denominator": 4,
    "rate": 1.0
  },
  "citation_correctness": {
    "numerator": 24,
    "denominator": 24,
    "rate": 1.0
  },
  "retrieval_top1_hit_rate": {
    "numerator": 13,
    "denominator": 24,
    "rate": 0.5417
  },
  "retrieval_top5_hit_rate": {
    "numerator": 21,
    "denominator": 24,
    "rate": 0.875
  },
  "latency": {
    "mean_ms": 1565.77,
    "p50_ms": 1895.48,
    "p95_ms": 3666.63,
    "max_ms": 3948.462
  }
}
```

固定 gold answerable correctness=21/24（87.50%）；Q23、Q24 的回答不完整保留。Q19 另有等價段落不在 frozen whitelist 的既有語意審查差異，語意審查 22/24（91.67%）不取代固定 gold 指標，不修改 gold。False refusal=0、unsafe answer=0；A～H 既有 regression 結果保留。本次沒有重新 UI 實測。Citation correctness 是 ref/support、role 與來源審查指標，不等同回答完整性或專業法規核定。

Latency：mean 1565.77 ms；P50 1895.48 ms；P95 3666.63 ms；max 3948.462 ms。

## KB／執行環境可比性

組織紀錄：`{"code": "HAPPY", "name": "幸福園長照中心（虛構）", "facility_type": "home", "actual_field_org": false}`。此回歸為既有測試 scope，不等於嘉安場域正式部署測試。

KB scope：32 current version IDs、2016 chunks；SHA256=`d624bfd9675ee8edec96c1635336704d05059cfaaf68f0ec0d04ade4f07d5be7`。本輪以 SQL READ ONLY 重算正文／locator／title／ID 的原快照摘要，完全一致；未更新 DB。實體備份含 version_ids／checksum manifest，但不含資料庫 dump，不應把 source 備份當成完整 KB 還原包。

本機 graph 回歸 latency 依原紀錄，不能直接等同 HTTP／登入／網路／現場併發 end-to-end latency。完整 methodology 保存在上述原 JSON。

## 已知問題與操作邊界

Q23：正確職責證據通過 gate 後在 focus／adjacent 選證階段未選入。Q24：短問法偏向督導範本，主要職掌未形成可用證據。兩者的非數值職責完整性未被線上 verification 判定；詳細原始 top10、全部 passed chunks、正文與 latency 見 `q23_q24_failure_analysis_20261008.md`。

本次僅建立兩份文件與實體備份，未修回答、不調 gate、不增加 top_k、不改 prompt／gold、不改風險／clarify／role／support 核心。

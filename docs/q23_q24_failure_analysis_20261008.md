# Q23／Q24 根因分析（2026-10-08）

建立時間：2026-10-08T11:08:54.438401+08:00。policy：`2026-10-08.local-fixes.1`。

分析來源為最新 `regression_local_fixes_20261008.json` 的第 1 輪（40 次），不是較早的 80 次 regression。未重跑 LLM、未重新召回、未修改程式／prompt／gold／KB。原始排序由 gate.candidates 的順序還原；前 8 名 combined 取 checks.retrieval，第 9／10 名未保存 combined，明確留空。文件、locator、完整正文以唯讀 DB 補足，2016 chunks 的快照 SHA256 與原回歸一致。數值微小 rounding 差異保留各紀錄原值。

JSON SHA256：`71bb84cd7bc727be416eb736fc305b7059743ba99bd8181a80ed9e63466bd235`；KB SHA256：`d624bfd9675ee8edec96c1635336704d05059cfaaf68f0ec0d04ade4f07d5be7`。

判斷：Q23 主因是 **evidence selection**，Q24 主因是 **retrieval**；兩題都有 **completeness verification** 缺口。實際 outcome=answer 並不代表內容完整，citation correctness=100% 也不等於 gold completeness=100%。

## Q23：居家服務督導員的主要工作職責有哪些？

### 1. Question／2. Frozen gold requirements

Question：居家服務督導員的主要工作職責有哪些？；style=formal；expected=answer。

Gold：居家服務督導員工作手冊；段落白名單：[14, 20, 29, 36, 37, 38, 39, 40, 41]。必要資訊組：`[["服務計畫"], ["督導", "協調", "服務品質"]]`。

至少涵蓋服務計畫，以及督導／協調／服務品質之一。白名單是可引用證據範圍，並非要求把九個 chunk 全部選入或逐段抄錄。第 14 段明載主要任務，足以支持最低要求；目前沒有證據顯示此 gold 不合理，未修改 gold。

### 3. Actual answer

actual_outcome=`answer`；correct_answer=`False`；final reason=`None`。

> 居督員肩負著促進服務使用者福祉與保障照顧現場安全的重要責任
> 居督員是居家式長照機構中承上啟下的關鍵角色

### 4. Original retrieval top 10

| rank | document | locator | chunk ID | combined | hybrid | coverage | vector | gate | reason |
|---:|---|---|---|---:|---:|---:|---:|---|---|
| 1 | 居家服務督導員工作手冊 | 第一節 居家服務督導員的角色功能與工作職掌｜第 21 段 | 2754e43e-4d04-4415-b1a8-8cb7bb41f52d | 0.608 | 0.458 | 0.558 | 0.3358 | True | body_relevant_and_base_signal |
| 2 | 居家服務督導員工作手冊 | 八、	倡導者｜第 36 段 | 68bb9de2-e99d-4db1-b36b-f6c4c7f4fe0c | 0.5763 | 0.4263 | 0.4983 | 0.3383 | True | body_relevant_and_base_signal |
| 3 | 居家服務督導員工作手冊 | 六、	居家服務督導員（下稱：居督員）｜第 14 段 | 6357817b-7278-4c78-b71c-9a55f7dea43b | 0.541 | 0.3909 | 0.4687 | 0.2959 | True | body_relevant_and_base_signal |
| 4 | 居家服務督導員工作手冊 | 二、	居督員教育訓練：｜第 27 段 | 1bfd09d3-7140-4a0c-b744-c3d6440d8d2d | 0.5206 | 0.3705 | 0.4348 | 0.292 | False | injection |
| 5 | 居家服務督導員工作手冊 | 第三章 居家服務督導｜第 284 段 | 66bbbb7f-6e32-48ca-ad89-d94af156304f | 0.4978 | 0.3478 | 0.3013 | 0.4046 | True | body_relevant_and_base_signal |
| 6 | 居家服務督導員工作手冊 | 十、	 服務的終止｜第 236 段 | 16bdf284-78e3-4453-b12c-d7c9800a018a | 0.4967 | 0.3467 | 0.4348 | 0.2391 | True | body_relevant_and_base_signal |
| 7 | 居家服務督導員工作手冊 | 第一章　緒論｜第 40 段 | fe503164-2903-487e-b06f-47ce53e28cd5 | 0.4951 | 0.3451 | 0.4091 | 0.2669 | True | body_relevant_and_base_signal |
| 8 | 居家服務督導員工作手冊 | 一、	居家服務督導員的核心工作倫理｜第 120 段 | 81d9c626-c158-40f5-ab37-14b9aae4bf46 | 0.4809 | 0.3308 | 0.3751 | 0.2767 | True | body_relevant_and_base_signal |
| 9 | 居家服務督導員工作手冊 | 第二節 居家服務督導員的基本知能｜第 43 段 | 54017aae-0e70-4ada-8521-097970ccdadc | 未保存 | 0.3284 | 0.4829 | 0.1395 | True | body_relevant_and_base_signal |
| 10 | 居家服務督導員工作手冊 | 第 1 段 | 8e4588b0-fa10-4111-aa65-5565b72d2d79 | 未保存 | 0.3234 | 0.3013 | 0.3505 | True | body_relevant_and_base_signal |

### 5. All gate-passed chunks

候選 613 個，通過 65 個。下表列出全部通過項目，rank 是原候選排序。

| rank | document／locator | chunk ID | body topic | gate reason | selected |
|---:|---|---|---:|---|---|
| 1 | 居家服務督導員工作手冊／第一節 居家服務督導員的角色功能與工作職掌｜第 21 段 | 2754e43e-4d04-4415-b1a8-8cb7bb41f52d | 0.7143 | body_relevant_and_base_signal | True |
| 2 | 居家服務督導員工作手冊／八、	倡導者｜第 36 段 | 68bb9de2-e99d-4db1-b36b-f6c4c7f4fe0c | 0.6429 | body_relevant_and_base_signal | False |
| 3 | 居家服務督導員工作手冊／六、	居家服務督導員（下稱：居督員）｜第 14 段 | 6357817b-7278-4c78-b71c-9a55f7dea43b | 0.6429 | body_relevant_and_base_signal | False |
| 5 | 居家服務督導員工作手冊／第三章 居家服務督導｜第 284 段 | 66bbbb7f-6e32-48ca-ad89-d94af156304f | 0.5 | body_relevant_and_base_signal | False |
| 6 | 居家服務督導員工作手冊／十、	 服務的終止｜第 236 段 | 16bdf284-78e3-4453-b12c-d7c9800a018a | 0.6429 | body_relevant_and_base_signal | False |
| 7 | 居家服務督導員工作手冊／第一章　緒論｜第 40 段 | fe503164-2903-487e-b06f-47ce53e28cd5 | 0.5714 | body_relevant_and_base_signal | False |
| 8 | 居家服務督導員工作手冊／一、	居家服務督導員的核心工作倫理｜第 120 段 | 81d9c626-c158-40f5-ab37-14b9aae4bf46 | 0.5714 | body_relevant_and_base_signal | False |
| 9 | 居家服務督導員工作手冊／第二節 居家服務督導員的基本知能｜第 43 段 | 54017aae-0e70-4ada-8521-097970ccdadc | 0.6429 | body_relevant_and_base_signal | False |
| 10 | 居家服務督導員工作手冊／第 1 段 | 8e4588b0-fa10-4111-aa65-5565b72d2d79 | 0.5 | body_relevant_and_base_signal | False |
| 11 | 居家服務督導員工作手冊／第二章 居家服務管理｜第 167 段 | f923c79d-eba5-4683-8f5c-8c2f5cb796b0 | 0.5 | body_relevant_and_base_signal | False |
| 12 | 居家服務督導員工作手冊／第三章 居家服務督導管理與工作方法｜第 292 段 | 7d8f6995-4e4b-4651-bc85-961218b3a64d | 0.5714 | body_relevant_and_base_signal | False |
| 13 | 居家服務督導員工作手冊／（六） 領有居家服務督導員職前訓練結業證明書，並於本辦法修正｜第 26 段 | 81e1916d-c7cc-4c74-953b-56b9eec9f884 | 0.4286 | body_relevant_and_base_signal | False |
| 14 | 居家服務督導員工作手冊／第四節 居家服務督導員工作倫理｜第 119 段 | ec7871f2-9b21-4545-b3ed-69c20e72f61c | 0.5 | body_relevant_and_base_signal | False |
| 15 | 居家服務督導員工作手冊／第二章　居家服務管理｜第 221 段 | 7f2edea8-a2df-4050-9c94-2a781ae779ca | 0.5 | body_relevant_and_base_signal | False |
| 16 | 居家服務督導員工作手冊／（五） 天然災害｜第 202 段 | 43e36ca5-faa0-4d15-b06b-da0f3f1e4bb1 | 0.5714 | body_relevant_and_base_signal | False |
| 17 | 居家服務督導員工作手冊／第一章　緒論｜第 39 段 | c0bda05c-3251-433a-b851-7b7ede31cf46 | 0.5 | body_relevant_and_base_signal | False |
| 18 | 居家服務督導員工作手冊／第四章 　風險管理｜第 394 段 | 74a0539b-16fa-455b-833b-f632776c1358 | 0.5 | body_relevant_and_base_signal | False |
| 19 | 居家服務督導員工作手冊／第四節 居家服務督導員工作倫理｜第 118 段 | b4b38d24-b6a0-4e64-80bc-a994193b1ce3 | 0.5714 | body_relevant_and_base_signal | False |
| 20 | 居家服務督導員工作手冊／八、 督導方式應依據服務使用者風險、照服員資歷與組織階段彈性｜第 305 段 | 991b9790-8239-4003-a0c1-66b8838f9582 | 0.5 | body_relevant_and_base_signal | False |
| 21 | 居家服務督導員工作手冊／（十）服務人力不足時，進行轉介至其他居家式長照機構。｜第 189 段 | 0e8e5eaf-e14c-421b-92ee-8b613b75ef99 | 0.5 | body_relevant_and_base_signal | False |
| 22 | 居家服務督導員工作手冊／二、 居督員負責中立調查、記錄處理歷程並提出結論｜第 377 段 | afb09edc-c988-4b7d-a889-842ed5db3c6a | 0.5 | body_relevant_and_base_signal | False |
| 23 | 居家服務督導員工作手冊／二、	成效評估機制｜第 321 段 | 7467fe93-d95e-4746-90b4-e127985192f0 | 0.5 | body_relevant_and_base_signal | False |
| 24 | 居家服務督導員工作手冊／（一） 收費或未開立收據｜第 281 段 | 647e1505-26a8-4df6-8d01-4449d74a438d | 0.5 | body_relevant_and_base_signal | False |
| 25 | 居家服務督導員工作手冊／第五節 基本法律認知與契約簽訂 136｜第 4 段 | 92b03d4f-8aff-44fd-be92-f0a969668af6 | 0.5714 | body_relevant_and_base_signal | False |
| 26 | 居家服務督導員工作手冊／第一章 緒論｜第 19 段 | 08f7c04a-fa9c-4526-a786-e2aeec7d3b9e | 0.5 | body_relevant_and_base_signal | True |
| 27 | 居家服務督導員工作手冊／三、服務期程、目標與確認｜第 595 段 | 6c085e9e-dd71-43b7-bd38-0c45424a57e5 | 0.5 | body_relevant_and_base_signal | False |
| 28 | 居家服務督導員工作手冊／（五） 其他經中央主管機關公告之服務類。｜第 10 段 | a33e861c-517f-4842-b378-15552ee73292 | 0.5 | body_relevant_and_base_signal | False |
| 29 | 居家服務督導員工作手冊／（二） 電訪記錄評估重點如下：｜第 215 段 | 94b8ee0a-37b0-42e1-91b1-935dbadac9e3 | 0.5714 | body_relevant_and_base_signal | False |
| 30 | 居家服務督導員工作手冊／（四） 靈活調整服務與創新｜第 117 段 | c333f04f-cd0a-4580-b950-b95ae3b0605b | 0.5 | body_relevant_and_base_signal | False |
| 31 | 居家服務督導員工作手冊／（十） 跨文化的領導：工作者應該能夠對其他專業提供多元文化資｜第 110 段 | b6647388-c501-4494-b0b7-8b036b475dc0 | 0.5714 | normalized_body_lexical_signal | False |
| 32 | 居家服務督導員工作手冊／第二章　居家服務管理｜第 194 段 | a0ca9d97-d9d5-466e-ae88-ece42dbb3907 | 0.5 | body_relevant_and_base_signal | False |
| 33 | 居家服務督導員工作手冊／(七) 結案｜第 271 段 | 268eb968-d577-4e80-a792-ec91a32dad31 | 0.5714 | body_relevant_and_base_signal | False |
| 34 | 居家服務督導員工作手冊／（六） 行政流程繁瑣。｜第 275 段 | 098482e5-d64b-481c-a2d8-72bd89758256 | 0.5 | body_relevant_and_base_signal | False |
| 35 | 居家服務督導員工作手冊／二、	照服員疑慮或壓力反應｜第 337 段 | 001ddf40-81e0-45a6-8502-8e3ae4891e58 | 0.5 | body_relevant_and_base_signal | False |
| 36 | 居家服務督導員工作手冊／第四章 風險管理｜第 381 段 | b56844eb-9e9a-440c-aea8-bc60beb52d92 | 0.5 | body_relevant_and_base_signal | False |
| 37 | 居家服務督導員工作手冊／二、	居家服務督導員對同僚的倫理原則｜第 129 段 | 51850940-dab9-4735-b631-623490480b53 | 0.5 | body_relevant_and_base_signal | False |
| 38 | 居家服務督導員工作手冊／一、	行政功能｜第 298 段 | d94bdd24-0b04-45f8-909e-678d78d422cd | 0.5 | body_relevant_and_base_signal | False |
| 39 | 居家服務督導員工作手冊／（三） 服務環境不安全，例如房屋頹圮、寵物具攻擊性等。｜第 175 段 | 1c2cafe5-b309-42b0-9862-ee56d2ddc93d | 0.5 | body_relevant_and_base_signal | False |
| 40 | 居家服務督導員工作手冊／九、	定期的修正｜第 235 段 | 66ef8218-b562-45ee-a610-c09b7c6c3889 | 0.5 | body_relevant_and_base_signal | False |
| 41 | 居家服務督導員工作手冊／四、	時間合理	→	不得因家屬｜第 64 段 | 84c0a9c8-9a11-457d-bf05-7fe760656c23 | 0.5 | body_relevant_and_base_signal | False |
| 42 | 居家服務督導員工作手冊／十、	 服務的終止｜第 237 段 | 3c07cdd0-c032-4bfa-8308-cb3fbc1a9d47 | 0.3571 | body_relevant_and_base_signal | False |
| 43 | 居家服務督導員工作手冊／（四） 依法合規｜第 150 段 | bc32aee1-2d17-48d6-8385-bc4211195653 | 0.5 | body_relevant_and_base_signal | False |
| 44 | 居家服務督導員工作手冊／第三章 居家服務督導管理與工作方法｜第 369 段 | 47615894-ee8d-4b8b-9f7e-2679f7d9978c | 0.4286 | body_relevant_and_base_signal | False |
| 45 | 居家服務督導員工作手冊／二、	書寫原則｜第 349 段 | 47a60ee4-34b5-4938-8f8d-8b1dffda527e | 0.5 | body_relevant_and_base_signal | False |
| 46 | 居家服務督導員工作手冊／（五） 瓣膜性心臟病｜第 553 段 | 77dd39f8-321a-400a-acd2-cdb02f9df28b | 0.5 | body_relevant_and_base_signal | False |
| 47 | 居家服務督導員工作手冊／（三） 溝通衝突：｜第 400 段 | 5cfc9b44-2c6b-41b5-835d-0dd9135b7c1f | 0.5 | body_relevant_and_base_signal | False |
| 48 | 居家服務督導員工作手冊／六、 瞭解相關法令：｜第 412 段 | 6a43804f-dda7-4393-9829-9f04b59a98c4 | 0.5 | body_relevant_and_base_signal | False |
| 49 | 居家服務督導員工作手冊／（三） 與服務使用者相關家屬｜第 74 段 | d5f40c71-881a-4ae1-85d1-14e3b35a8a2c | 0.5 | body_relevant_and_base_signal | False |
| 50 | 居家服務督導員工作手冊／（三）	意見交流：｜第 390 段 | cf8bd78b-9163-4792-8b1f-0f06e1ad5276 | 0.5 | body_relevant_and_base_signal | False |
| 51 | 居家服務督導員工作手冊／（二） 照顧責任問題｜第 138 段 | edd56e6b-6507-469c-8ae2-af09f5cd6d18 | 0.5 | body_relevant_and_base_signal | False |
| 52 | 居家服務督導員工作手冊／第四章 　風險管理｜第 490 段 | ca08dc5f-5db2-4a71-bb39-8d5954148b33 | 0.5714 | body_relevant_and_base_signal | False |
| 53 | 居家服務督導員工作手冊／第四章 　風險管理｜第 472 段 | f99ec66e-800d-4351-af45-99ceae5305b2 | 0.5 | body_relevant_and_base_signal | False |
| 54 | 居家服務督導員工作手冊／二、	標準化工具強化稽核品質｜第 354 段 | d28d7d2c-e96d-43a0-805b-69749e206663 | 0.5 | body_relevant_and_base_signal | False |
| 55 | 居家服務督導員工作手冊／第二章　居家服務管理｜第 225 段 | cabfbb16-59d5-4928-9813-5182a32130ed | 0.5 | body_relevant_and_base_signal | False |
| 56 | 居家服務督導員工作手冊／一、照顧問題評估｜第 591 段 | 8f4f17ed-c463-4ff5-8bc0-57aa582cac50 | 0.5714 | body_relevant_and_base_signal | False |
| 57 | 居家服務督導員工作手冊／三、	溝通協調｜第 84 段 | 94a6804d-5eae-4a03-84a3-da1f1523aa4c | 0.5 | body_relevant_and_base_signal | False |
| 58 | 居家服務督導員工作手冊／四、	傾聽與理解訴求｜第 327 段 | 79d445b4-0b18-4d6e-9e0b-a654f0c1e10c | 0.5 | body_relevant_and_base_signal | False |
| 60 | 居家服務督導員工作手冊／（三） 依簽訂合約持續穩定提供服務，持續追蹤使用者身體狀況、｜第 586 段 | ad826ce5-c5e1-4a9c-97d6-111fcba21c82 | 0.5 | body_relevant_and_base_signal | False |
| 61 | 居家服務督導員工作手冊／（一） 用於病原體侵犯人體皮膚或粘膜的傳染病時所採取的隔離方｜第 467 段 | 2175f7f9-56ee-4815-96ce-6bea2ffbf49e | 0.5 | body_relevant_and_base_signal | False |
| 62 | 居家服務督導員工作手冊／（二） 綜上所述，建議處理方式如下：｜第 511 段 | a51799f8-dec2-4650-9fa0-4d2d7da6d99e | 0.5 | body_relevant_and_base_signal | False |
| 114 | 附件一　居家式長照機構設立標準表／二、人員｜第 4 段 | c5f27ec9-493a-4a3e-81ed-18c5826808b2 | 0.4286 | body_relevant_and_base_signal | False |
| 140 | 1.長照專業服務操作指引-觀念篇_公告／二、專業服務團隊成員及其職責｜第 43 段 | 4f95808e-4e59-4da2-9bfc-121b868a3e35 | 0.5 | body_relevant_and_base_signal | False |
| 146 | 附件一 長照人員資格／六、 高級中等以上學校畢業，領有教｜第 6 段 | 13f54bc9-eb24-470f-ab68-4ed8251bbc04 | 0.4286 | body_relevant_and_base_signal | False |
| 172 | 附件一 長照人員資格／六、 領有居家服務督導員職前訓練結｜第 11 段 | 852b86eb-8f87-457d-a5bb-60d6f9569276 | 0.5 | body_relevant_and_base_signal | False |
| 180 | 長期照顧服務人員訓練認證繼續教育及登錄辦法／第 2 條 | 0c080889-ee05-4b43-a9c0-673061ed0e00 | 0.5 | body_relevant_and_base_signal | False |

### 6. Selected evidence（原始送入 LLM 正文）

**E1 — 居家服務督導員工作手冊／第一節 居家服務督導員的角色功能與工作職掌｜第 21 段**；`2754e43e-4d04-4415-b1a8-8cb7bb41f52d`；version=`Phase1_KB_2026-10-07_v1`。

> 第一節 居家服務督導員的角色功能與工作職掌
> 居督員做為居家式長照機構中承上啟下的關鍵角色，肩負著促進服務使用者福祉
> 與保障照顧現場安全的重要責任。 本節將分別說明居督員之資格條件、 資格訓練計畫、
> 主要角色功能與工作職掌內容。
> 壹、	 居家服務督導員的資格及教育訓練
> 依據「長期照顧服務人員訓練認證繼續教育及登錄辦法 ( 下稱長照人員辦法 )」
> 所訂，居督員相關規定如下：

**E2 — 居家服務督導員工作手冊／第一章 緒論｜第 19 段**；`08f7c04a-fa9c-4526-a786-e2aeec7d3b9e`；version=`Phase1_KB_2026-10-07_v1`。

> 第一章 緒論
> 9
> <!-- 第 10 頁 -->
> 居家服務督導員工作手冊
> 10
> 緒論
> 隨著人口老化及少子化，家庭照顧功能減弱，為因應失能、失智人口增加所衍生
> 之長照需求，政府為滿足家庭照顧多元化需求，規劃長期照顧服務，對預期或已達六
> 個月以上無法生活自理的民眾， 由長照服務人員及單位， 提供各種照顧及專業服務 ( 包
> 含居家服務、日間照顧、家庭托顧、小規模多機能服務、專業服務 )、輔具租借、購
> 買及居家無障礙環境改善、交通接送及喘息服務等，以回應高齡化社會的長照問題。
> 其中居家服務係長照十年計畫時期即推展之服務，其工作模式最具成熟，民眾不
> 僅獲得可近性及可選擇性的服務，且能獲得有尊嚴及自主的照顧方式，留在自己熟悉
> 的住所中，維持其原有的生活習慣，是較符合人性化需求及兼顧受照顧者自主照顧的
> 方式，居家服務是獲得滿意度高的長照服務。
> 居家服務是透過照服員到宅至服務使用者家中服務，但其工作時間安排、服務項
> 目規劃、服務關係建立、異常事件處理、服務品質的維護及跨專業溝通與協調等事務

Evidence selection／focus 原始紀錄：

```json
{
  "focus": {
    "enabled": true,
    "document_id": "52a0c339-01f4-4eb2-b9c0-5c62355f70be",
    "title": "居家服務督導員工作手冊",
    "top_score": 0.608,
    "best_other_score": 0.3252
  },
  "selection": {
    "requested_field": null,
    "fact_chunk_ids": [],
    "previous_chunk_ids": [
      "2754e43e-4d04-4415-b1a8-8cb7bb41f52d",
      "08f7c04a-fa9c-4526-a786-e2aeec7d3b9e"
    ],
    "selected_chunk_ids": [
      "2754e43e-4d04-4415-b1a8-8cb7bb41f52d",
      "08f7c04a-fa9c-4526-a786-e2aeec7d3b9e"
    ]
  },
  "size": {
    "chunks": 2,
    "chars": 629
  }
}
```

Gold chunk 去向（含未召回與未通過）：

| locator | chunk ID | original rank | gate | selected |
|---|---|---:|---|---|
| 二、	服務計畫擬定者｜第 29 段 | 1967f1c8-2a79-449e-b44e-b22545a115e8 | 224 | False / body_topic_missing | False |
| 第一章　緒論｜第 41 段 | 4bc7a464-41e2-4d36-9e6c-8bb41b213f67 | 117 | False / base_signal_insufficient | False |
| 六、	居家服務督導員（下稱：居督員）｜第 14 段 | 6357817b-7278-4c78-b71c-9a55f7dea43b | 3 | True / body_relevant_and_base_signal | False |
| 八、	倡導者｜第 36 段 | 68bb9de2-e99d-4db1-b36b-f6c4c7f4fe0c | 2 | True / body_relevant_and_base_signal | False |
| 第一章 緒論｜第 20 段 | 6a9a9333-a02c-4352-a50f-b1d9b93a5454 | 118 | False / body_topic_missing | False |
| 八、	倡導者｜第 38 段 | 8e57d3ec-3fd2-43bf-9d87-6ca7c6053da9 | 174 | False / body_topic_missing | False |
| 第一章　緒論｜第 39 段 | c0bda05c-3251-433a-b851-7b7ede31cf46 | 17 | True / body_relevant_and_base_signal | False |
| 八、	倡導者｜第 37 段 | e3ca6a47-c1cc-46bb-9f64-4f8fd0500f33 | 154 | False / body_topic_missing | False |
| 第一章　緒論｜第 40 段 | fe503164-2903-487e-b06f-47ce53e28cd5 | 7 | True / body_relevant_and_base_signal | False |

### 7–10. 缺漏所在層與 chunk 邊界

**7：是，正確證據已存在、召回且通過 gate，但未選入。** 第 14 段在 rank 3（combined=0.541），內文直接列服務計畫、照服員督導、協調、電訪／家訪、品質與緊急事故職責；rank 2／7／17 的 gold 段落亦通過。不是 KB 缺資料，也不是主要依據被 gate 擋掉。

**8：selected evidence 不足以完整滿足 gold。** E1 是章節引言，不是實際職掌；E2 有排班、項目規劃、品質與跨專業協調，但沒有完整接上的責任主體，也沒有服務計畫依據。LLM 只引用 E1 產生抽象角色描述，亦未利用 E2 的局部工作資訊；不能把主因說成「完整證據已送入但純 LLM 漏答」。

**9：verification 有局部 support／ref／role 檢查，但未檢查工作職責答案的概念完整性。** requested_field=null、fact_chunk_ids=[]；兩個 claim support 為 0.929／0.9 且 roles passed，故抽象但可支持的陳述被接受。gold 的 fact_anchors_pass=false 是事後 regression 檢查，不是線上完整性拒絕。

**10：涉及 adjacency 與 chunk 邊界。** evidence_focus=true；以第 21 段為 anchor 的 nearest-seq 視窗（top_k=5）包含 19～23 段，再以 topic 篩選，留下 21／19。第 14 段離 anchor 七個 seq，不在此視窗；已通過的高價值 chunk 沒被非數值欄位的 prioritize_admitted 補回。第 19 段末句停在「等事務」，第 20 段才接「係由居督員協助處理」。第 20 段 body_topic=0.2857，未通過 gate，亦不符相鄰 topic 門檻；未補足完整主詞／職責段落。最後只用了 2 chunks，沒有填滿 top_k=5；單純增加容量不是已證明的修法。

**failure class：主因 evidence selection；次因 completeness verification；LLM generation 為附帶缺漏。** retrieval／gate 不是阻止最低要求證據的主要層；gold issue 未發現。

核心主要任務原文（第 14 段；KB 已有）：

> 六、	居家服務督導員（下稱：居督員）
> 依「長期照顧服務機構設立標準」，於居家式長照機構中設置之專任人員，並規
> 定為每服務人數 60 人應置 1 名居督員。其主要任務係負責擬定「服務計畫」、督導
> 照服員提供適切之居家服務， 建立督導機制、 定期開督導會議增進照服員之服務能力、
> 安排、協調照顧服務、並定期透過電訪、家訪追蹤照服員工作狀況及執行情形，以管
> 理及督導照服員提供穩定之居家服務， 維持服務品質， 亦須具有處理緊急事故之職責。

### 11. Recorded latency

```json
{
  "total_latency_ms": 2372.836,
  "retrieval_latency_ms": 1024.796,
  "llm_latency_ms": 1340.007,
  "verification_latency_ms": 2.12,
  "timings_ms": {
    "retrieve": 608,
    "evidence_prepare": 416,
    "generate": 1340,
    "graph_total": 2372
  }
}
```

### 12. LLM candidate／verification audit

```json
{
  "llm_candidate": {
    "claims": [
      {
        "text": "居督員肩負著促進服務使用者福祉與保障照顧現場安全的重要責任",
        "citation_refs": [
          "E1"
        ]
      },
      {
        "text": "居督員是居家式長照機構中承上啟下的關鍵角色",
        "citation_refs": [
          "E1"
        ]
      }
    ],
    "needs_human": false,
    "conflict": false,
    "reason": "",
    "raw_ok": true,
    "metrics": {
      "load_duration": 10465200,
      "prompt_eval_duration": 294542000,
      "eval_duration": 1024210000,
      "total_duration": 1338329600,
      "prompt_eval_count": 1492,
      "eval_count": 129
    }
  },
  "verification_claims": [
    {
      "refs": [
        "E1"
      ],
      "unknown_refs": [],
      "support": 0.929,
      "roles": {
        "passed": true,
        "mismatches": []
      },
      "accepted": true
    },
    {
      "refs": [
        "E1"
      ],
      "unknown_refs": [],
      "support": 0.9,
      "roles": {
        "passed": true,
        "mismatches": []
      },
      "accepted": true
    }
  ],
  "citation_correctness": {
    "passed": true,
    "refs_support_pass": true,
    "expected_chunk_selected": false,
    "fact_anchors_pass": false,
    "status": "References/support + role verification + agent source review; not expert sign-off"
  },
  "final_reason": null,
  "reason_detail": null
}
```

## Q24：居督主要做什麼？

### 1. Question／2. Frozen gold requirements

Question：居督主要做什麼？；style=short；expected=answer。

Gold：居家服務督導員工作手冊；段落白名單：[14, 20, 29, 36, 37, 38, 39, 40, 41]。必要資訊組：`[["服務計畫"], ["督導", "協調", "服務品質"]]`。

至少涵蓋服務計畫，以及督導／協調／服務品質之一。白名單是可引用證據範圍，並非要求把九個 chunk 全部選入或逐段抄錄。第 14 段明載主要任務，足以支持最低要求；目前沒有證據顯示此 gold 不合理，未修改 gold。

### 3. Actual answer

actual_outcome=`answer`；correct_answer=`False`；final reason=`None`。

> 居督員會參與團體督導會議，並在個案督導中引導受督者進行自我探索與察覺，同時提供工作表現的支持與肯定。
> 在團體督導中，居督員會處理如業務策略擬定、年度檢討與未來展望等主題，並可能涉及居家服務資訊系統的優化作業。
> 在個案督導中，居督員會引導受督者思考如何避免重蹈覆轍，學習停下來再判斷問題，並鼓勵受督者的自我探索過程。

### 4. Original retrieval top 10

| rank | document | locator | chunk ID | combined | hybrid | coverage | vector | gate | reason |
|---:|---|---|---|---:|---:|---:|---:|---|---|
| 1 | 居家服務督導員工作手冊 | 二、 身體狀況及家庭關係穩定，生活與工作平衡點因上述原因尚在｜第 599 段 | 6737b6d7-ea47-4688-b516-0b4a919917aa | 0.3471 | 0.3471 | 0.5536 | 0.0948 | True | body_relevant_and_base_signal |
| 2 | 居家服務督導員工作手冊 | 二、 身體狀況及家庭關係穩定，生活與工作平衡點因上述原因尚在｜第 598 段 | ba19c013-237f-4cdf-b4e3-d7be74998458 | 0.2617 | 0.2617 | 0.3951 | 0.0987 | True | body_relevant_and_base_signal |
| 3 | 居家服務督導員工作手冊 | 第一節 居家服務督導員的角色功能與工作職掌｜第 21 段 | 2754e43e-4d04-4415-b1a8-8cb7bb41f52d | 0.2184 | 0.2184 | 0.3363 | 0.0743 | False | base_signal_insufficient |
| 4 | 居家服務督導員工作手冊 | 第三章 居家服務督導管理與工作方法｜第 292 段 | 7d8f6995-4e4b-4651-bc85-961218b3a64d | 0.2134 | 0.2134 | 0.3363 | 0.0632 | False | base_signal_insufficient |
| 5 | 居家服務督導員工作手冊 | 十、	 服務的終止｜第 236 段 | 16bdf284-78e3-4453-b12c-d7c9800a018a | 0.2104 | 0.2105 | 0.3363 | 0.0567 | False | base_signal_insufficient |
| 6 | 居家服務督導員工作手冊 | 二、	群突發事件處理：｜第 476 段 | 2b9c7964-f555-4896-9d66-2664bf8c1e02 | 0.2092 | 0.2092 | 0.3363 | 0.0539 | False | base_signal_insufficient |
| 7 | 居家服務督導員工作手冊 | 第二章　居家服務管理｜第 238 段 | ed827e1d-66aa-43bf-9ef0-ebb0af17d39a | 0.1992 | 0.1992 | 0.3363 | 0.0317 | False | base_signal_insufficient |
| 8 | 居家服務督導員工作手冊 | 第三節 家庭溝通及處遇技巧｜第 222 段 | e6bdb942-c1fc-4472-8a7b-60fd76cb8991 | 0.1989 | 0.1989 | 0.3363 | 0.031 | False | base_signal_insufficient |
| 9 | 居家服務督導員工作手冊 | 第五節 基本法律認知與契約簽訂｜第 485 段 | 312245a6-f904-4cd2-8ad2-c03ccf2bdacd | 未保存 | 0.1937 | 0.3363 | 0.0193 | False | base_signal_insufficient |
| 10 | 居家服務督導員工作手冊 | (一) 居督員評估服務使用者｜第 264 段 | 70610c22-a78e-46df-b874-b0c94edeee24 | 未保存 | 0.193 | 0.3363 | 0.0178 | False | base_signal_insufficient |

### 5. All gate-passed chunks

候選 90 個，通過 2 個。下表列出全部通過項目，rank 是原候選排序。

| rank | document／locator | chunk ID | body topic | gate reason | selected |
|---:|---|---|---:|---|---|
| 1 | 居家服務督導員工作手冊／二、 身體狀況及家庭關係穩定，生活與工作平衡點因上述原因尚在｜第 599 段 | 6737b6d7-ea47-4688-b516-0b4a919917aa | 0.5 | body_relevant_and_base_signal | True |
| 2 | 居家服務督導員工作手冊／二、 身體狀況及家庭關係穩定，生活與工作平衡點因上述原因尚在｜第 598 段 | ba19c013-237f-4cdf-b4e3-d7be74998458 | 0.25 | body_relevant_and_base_signal | True |

### 6. Selected evidence（原始送入 LLM 正文）

**E1 — 居家服務督導員工作手冊／二、 身體狀況及家庭關係穩定，生活與工作平衡點因上述原因尚在｜第 599 段**；`6737b6d7-ea47-4688-b516-0b4a919917aa`；version=`Phase1_KB_2026-10-07_v1`。

> 二、 身體狀況及家庭關係穩定，生活與工作平衡點因上述原因尚在努力中。
> □繼續列管
> □解除列管
> 本次團體紀錄
> 團督目的
> 團督內容
> 團督照片
> 器　　材 下次團督辦理建議
> 紀　　錄 主　　管
> <!-- 第 173 頁 -->
> 173
> 附錄
> OO 居家式長照機構
> 團體督導會議紀錄	( 書寫範本僅供參考 )
> 團督主題 業務策略擬定 - 年度檢討與未來展望
> 團督日期 1 1 3年1 2月1 5日 團督時間 19：00 － 20：00
> 主席／團督帶領者 李美麗 團督地點 機構會議室
> 出席狀況 出席總人數：50 人
> 參與成員：全體照服員、居督員、業務負責人、主任
> 上次會議決議執行情況
> 案由 決 議 執行情形 列管情形
> 居家服務資訊系統
> 優化作業
> 系統 APP 軟體優化彙
> 整建議如下，將與資
> 訊廠商提出需求。
> 1. 上下班打卡時間
> 提示功能優化。
> 2. 系統 APP 軟體介
> 面 ，因手機作業
> 系統不同有二個
> 版本 ，調整統一
> 版本。
> 3. 體溫測量設定二
> 次，更改為一次。
> 因為新系統導入初
> 期，因此將於系統穩
> 定操作後，再向系統
> 廠商提出優化需求，

**E2 — 居家服務督導員工作手冊／二、 身體狀況及家庭關係穩定，生活與工作平衡點因上述原因尚在｜第 598 段**；`ba19c013-237f-4cdf-b4e3-d7be74998458`；version=`Phase1_KB_2026-10-07_v1`。

> 二、 身體狀況及家庭關係穩定，生活與工作平衡點因上述原因尚在努力中。
> 督導者回覆：
> 引導受督者思考如何在新的開始，不再重蹈覆轍，受訪者經過引導後與省思後，表達自己容
> 易太快做決定而缺少全面分析與溝通協調，應該學習讓自己停一下，再判斷問題，這樣較容
> 易找到問題根源，而不是解決問題表面但問題卻不斷循環，也造成自己一直深陷問題循環。
> 督導者鼓勵與肯定受訪者自我探索過程與自我察覺能力，並且給予受督者這段時間工作表現
> 的支持與肯定，最後提醒受督者要記得先照顧好自己為重。
> 追蹤與結案：
> 受督者表示無須追蹤，若需協助會自行尋求機構所提供的員工關懷管道或與主管提出需求，
> 因此先行結案。
> 受督者    督導者     主管
> <!-- 第 172 頁 -->
> 居家服務督導員工作手冊
> 172
> 附錄五  團體督導記錄參考表單及範例
> OO 居家式長照機構
> 團體督導會議紀錄	( 格式僅供參考 )
> 團督主題
> 團督日期 團督時間
> 主席／團督帶領者 團督地點
> 出席狀況
> 出席總人數：　　人
> 參與成員：
> 上次會議決議執行情況
> 案由 決 議 執行情形 列管情形

Evidence selection／focus 原始紀錄：

```json
{
  "focus": {
    "enabled": false
  },
  "selection": {
    "requested_field": null,
    "fact_chunk_ids": [],
    "previous_chunk_ids": [
      "6737b6d7-ea47-4688-b516-0b4a919917aa",
      "ba19c013-237f-4cdf-b4e3-d7be74998458"
    ],
    "selected_chunk_ids": [
      "6737b6d7-ea47-4688-b516-0b4a919917aa",
      "ba19c013-237f-4cdf-b4e3-d7be74998458"
    ]
  },
  "size": {
    "chunks": 2,
    "chars": 939
  }
}
```

Gold chunk 去向（含未召回與未通過）：

| locator | chunk ID | original rank | gate | selected |
|---|---|---:|---|---|
| 二、	服務計畫擬定者｜第 29 段 | 1967f1c8-2a79-449e-b44e-b22545a115e8 | 未在候選中 | 未評估 | False |
| 第一章　緒論｜第 41 段 | 4bc7a464-41e2-4d36-9e6c-8bb41b213f67 | 13 | False / base_signal_insufficient | False |
| 六、	居家服務督導員（下稱：居督員）｜第 14 段 | 6357817b-7278-4c78-b71c-9a55f7dea43b | 12 | False / base_signal_insufficient | False |
| 八、	倡導者｜第 36 段 | 68bb9de2-e99d-4db1-b36b-f6c4c7f4fe0c | 63 | False / body_topic_missing | False |
| 第一章 緒論｜第 20 段 | 6a9a9333-a02c-4352-a50f-b1d9b93a5454 | 28 | False / body_topic_missing | False |
| 八、	倡導者｜第 38 段 | 8e57d3ec-3fd2-43bf-9d87-6ca7c6053da9 | 未在候選中 | 未評估 | False |
| 第一章　緒論｜第 39 段 | c0bda05c-3251-433a-b851-7b7ede31cf46 | 未在候選中 | 未評估 | False |
| 八、	倡導者｜第 37 段 | e3ca6a47-c1cc-46bb-9f64-4f8fd0500f33 | 未在候選中 | 未評估 | False |
| 第一章　緒論｜第 40 段 | fe503164-2903-487e-b06f-47ce53e28cd5 | 64 | False / body_topic_missing | False |

### 7–10. 缺漏所在層與 chunk 邊界

**7：KB 有正確依據，但本題可用候選不足。** 九個 gold chunks 中僅 5 個進原始候選，且皆未通過 gate；第 14 段不在候選中。不能說「完整正確證據已通過，只差 evidence selection」。

**8：否，selected evidence 不足。** E1／E2 是附錄督導會議與個案督導範本，不是主要職責條文；缺服務計畫等最低必要資訊。LLM 把範本活動概括成核心工作，屬題意覆蓋不足及來源情境過度推論，不是只漏讀充分證據。

**9：同樣沒有職責概念完整性檢查。** 三個 claims support=0.535／0.659／0.548，roles 都 passed、accepted=true；這些局部檢查未證明答案回答「主要做什麼」或涵蓋服務計畫。事後 fact_anchors_pass=false 不會回溯阻止原 answer。

**10：相鄰選取不是本題主要原因。** evidence_focus=false，僅 2 chunks 通過且全選入。第 598／599 段相鄰，但属于範本；第 596 段有受督者／督導者身份，第 598 段正文未帶此表頭。唯讀檢視可見範本中受督者職稱為居督員、督導者職稱為業務負責人；LLM 卻把「督導者」引導受督者的行為歸為居督員。這是跨 chunk 情境／主體歸因疑點，現有 role verification 在已選 fragment 上通過，不能據此保證整份範本的角色解讀正確。本輪只記錄，不修改角色規則。

**failure class：主因 retrieval；次因 completeness verification；LLM generation（範本概括、主體情境）為附帶問題。** gate 對部分職責相關候選標示 base_signal_insufficient，但主要任務段落根本未召回，因此不以降低 gate 為結論。evidence selection 已選盡 passed chunks，不是單獨容量問題；gold issue 未發現。

短句 title_topic=0，前兩名 coverage=0.5536／0.3951 而 vector=0.0948／0.0987；對照正式問法 title_topic=0.5 且主要任務進 rank 3，顯示短問法的職掌語意／角色縮寫與範本 token 匹配偏差。此處為依召回差異的根因推論，未以新的 retrieve／prompt 實驗證明任何修法。

核心主要任務原文（第 14 段；KB 已有）：

> 六、	居家服務督導員（下稱：居督員）
> 依「長期照顧服務機構設立標準」，於居家式長照機構中設置之專任人員，並規
> 定為每服務人數 60 人應置 1 名居督員。其主要任務係負責擬定「服務計畫」、督導
> 照服員提供適切之居家服務， 建立督導機制、 定期開督導會議增進照服員之服務能力、
> 安排、協調照顧服務、並定期透過電訪、家訪追蹤照服員工作狀況及執行情形，以管
> 理及督導照服員提供穩定之居家服務， 維持服務品質， 亦須具有處理緊急事故之職責。

### 11. Recorded latency

```json
{
  "total_latency_ms": 2604.468,
  "retrieval_latency_ms": 196.851,
  "llm_latency_ms": 2384.953,
  "verification_latency_ms": 15.11,
  "timings_ms": {
    "retrieve": 116,
    "evidence_prepare": 80,
    "generate": 2384,
    "graph_total": 2604
  }
}
```

### 12. LLM candidate／verification audit

```json
{
  "llm_candidate": {
    "claims": [
      {
        "text": "居督員會參與團體督導會議，並在個案督導中引導受督者進行自我探索與察覺，同時提供工作表現的支持與肯定。",
        "citation_refs": [
          "E1",
          "E2"
        ]
      },
      {
        "text": "在團體督導中，居督員會處理如業務策略擬定、年度檢討與未來展望等主題，並可能涉及居家服務資訊系統的優化作業。",
        "citation_refs": [
          "E1"
        ]
      },
      {
        "text": "在個案督導中，居督員會引導受督者思考如何避免重蹈覆轍，學習停下來再判斷問題，並鼓勵受督者的自我探索過程。",
        "citation_refs": [
          "E2"
        ]
      }
    ],
    "needs_human": false,
    "conflict": false,
    "reason": "",
    "raw_ok": true,
    "metrics": {
      "load_duration": 9448100,
      "prompt_eval_duration": 399689000,
      "eval_duration": 1962884000,
      "total_duration": 2381606300,
      "prompt_eval_count": 1785,
      "eval_count": 218
    }
  },
  "verification_claims": [
    {
      "refs": [
        "E1",
        "E2"
      ],
      "unknown_refs": [],
      "support": 0.535,
      "roles": {
        "passed": true,
        "mismatches": []
      },
      "accepted": true
    },
    {
      "refs": [
        "E1"
      ],
      "unknown_refs": [],
      "support": 0.659,
      "roles": {
        "passed": true,
        "mismatches": []
      },
      "accepted": true
    },
    {
      "refs": [
        "E2"
      ],
      "unknown_refs": [],
      "support": 0.548,
      "roles": {
        "passed": true,
        "mismatches": []
      },
      "accepted": true
    }
  ],
  "citation_correctness": {
    "passed": true,
    "refs_support_pass": true,
    "expected_chunk_selected": false,
    "fact_anchors_pass": false,
    "status": "References/support + role verification + agent source review; not expert sign-off"
  },
  "final_reason": null,
  "reason_detail": null
}
```

## 本輪限制與凍結

以上僅原回歸紀錄、核心 source 路徑與 KB 唯讀分析；沒有修改 top_k、prompt、gold、risk、clarify、gate、retrieval、role／support verification 或知識庫。未新增任何修正，亦未重新生成答案。下一輪若授權修正，應分別驗證 Q23 的已通過證據保留與 Q24 的職掌召回／來源情境，再評估概念完整性；本報告不預先指定演算法改動。

目前版本備份：`C:\aa\ltc_care_installer_20260912\ltc_care\backups\pre_field_freeze_20261008_110854`。凍結紀錄見 `pre_field_freeze_20261008.md`。

# RAG Optimization Parameter Registry

從目前 aa 程式與已解析 runtime 設定盤點；未修改任何參數。機器可讀完整值、規則正文、search space 及備註見 `quality_tests/optimization/parameters.json`。
A=未來離線數值搜尋；B=離散比較；C=人工規則設計；D=不建議自動調整。建議 search space 不是 production 現值。
實際 hash embedding model 與設定 EMBEDDING_MODEL 不同；沒有 cross-encoder reranker 或獨立 rerank score。prompt 原本沒有具名版本，Phase1 只新增派生 fingerprint。

| parameter_id | 層 | 現值／規則 | 分類 | 可設定 | 程式位置 |
|---|---|---|---|---|---|
| chunk.target | ingest | 400 | A | False | backend/app/services/ingest.py:16 |
| chunk.max | ingest | 700 | A | False | backend/app/services/ingest.py:15 |
| chunk.overlap | ingest | 0 | B | False | backend/app/services/ingest.py:141 |
| embedding.provider | embedding | "hash" | D | True | backend/app/providers/embedding.py:91 |
| embedding.model | embedding | "hash-ngram-1024" | D | True | backend/app/providers/embedding.py:40 |
| embedding.configured_model | embedding | "bge-m3" | D | True | backend/app/providers/embedding.py:96 |
| embedding.dimension | embedding | 1024 | D | True | backend/app/providers/embedding.py:39 |
| policy.candidate_k | retrieval | 50 | A | False | backend/app/services/qa_policy.py:29 |
| policy.top_k | retrieval | 5 | A | False | backend/app/services/qa_policy.py:28 |
| policy.lexical_weight | retrieval | 0.55 | A | False | backend/app/services/qa_policy.py:30 |
| policy.min_top_coverage | retrieval | 0.18 | A | False | backend/app/services/qa_policy.py:31 |
| policy.min_combined | retrieval | 0.24 | A | False | backend/app/services/qa_policy.py:32 |
| policy.min_evidence_score | retrieval | 0.16 | A | False | backend/app/services/qa_policy.py:33 |
| policy.min_support | answer | 0.45 | D | False | backend/app/services/qa_policy.py:34 |
| policy.min_gate_vector | gate | 0.52 | D | False | backend/app/services/qa_policy.py:49 |
| policy.min_gate_body_topic | gate | 0.5 | D | False | backend/app/services/qa_policy.py:50 |
| policy.min_gate_title_topic | gate | 0.8 | D | False | backend/app/services/qa_policy.py:51 |
| policy.min_gate_rule_topic | gate | 0.8 | D | False | backend/app/services/qa_policy.py:52 |
| retrieval.vector_weight | retrieval | 0.44999999999999996 | A | False | backend/app/services/retrieval.py:447 |
| retrieval.hybrid | retrieval | {"raw": "lexical_weight*coverage+(1-lexical_weight)*max(vector,0)", "normalized": "lexical_weight*normalized_coverage+(1-lexical_weight)*max… | C | False | backend/app/services/retrieval.py:448 |
| ranking.absent_token_factor | retrieval | 0.6 | A | False | backend/app/services/retrieval.py:60 |
| ranking.exact_title_bonus | retrieval | 0.25 | A | False | backend/app/services/retrieval.py:61 |
| ranking.fuzzy_title_bonus_weight | retrieval | 0.3 | A | False | backend/app/services/retrieval.py:62 |
| ranking.fuzzy_title_min_coverage | retrieval | 0.35 | A | False | backend/app/services/retrieval.py:63 |
| ranking.permission_intent_bonus | retrieval | 0.22 | A | False | backend/app/services/retrieval.py:64 |
| ranking.intent_conditions | retrieval | "def _ranking_bonuses(question: str, title: str, chunk_text: str) -> tuple[float, float, float]:\n    \"\"\"主題相關性、標題分、意圖分；expanded query 不參與… | C | False | backend/app/services/retrieval.py:103 |
| retrieval.title_candidates | retrieval | {"minimum_overlap_bigrams": 2, "minimum_title_coverage": 0.35, "document_chunks": "all eligible chunks of matched document"} | C | False | backend/app/services/retrieval.py:357 |
| retrieval.reranking | retrieval | {"model": null, "algorithm": "heuristic combined score; medication scope+drug flag first, then combined DESC"} | B | False | backend/app/services/retrieval.py:491 |
| adjacency.service_span | retrieval | {"anchor_to_seq_plus": 4, "maximum_chunks": 5, "stop": "next BA code", "eligibility": "same eligible version; explicit purpose includes drug… | C | False | backend/app/services/retrieval.py:411 |
| adjacency.answer_focus | answer | {"distance": "ORDER BY ABS(seq-anchor.seq), seq", "limit": "policy.top_k", "exclude_intents": "permission/reporting/record", "body_topic_thr… | C | False | backend/app/services/qa_graph.py:225 |
| answer.focus_min | answer | 0.45 | A | False | backend/app/services/qa_graph.py:209 |
| answer.focus_margin | answer | 0.05 | A | False | backend/app/services/qa_graph.py:212 |
| gate.reporting_threshold | gate | {"dedicated_numeric_threshold": null, "shared_procedure_topic_min": 0.8, "explicit_frontline_route": "care_reporting AND reporting_duty(body… | D | False | backend/app/services/retrieval_gate.py:100 |
| gate.intent_routes | gate | "def assess_evidence(question: str, chunk: RetrievedChunk, policy: QaPolicy, *, check_injection: bool = True) -> GateDecision:\n    \"\"\"Ne… | D | False | backend/app/services/retrieval_gate.py:50 |
| gate.rule_window | gate | {"stride_chars": 160, "window_chars": 320} | C | False | backend/app/services/retrieval_gate.py:63 |
| risk.medication_and_other | risk | [{"code": "emergency", "pattern": "(昏倒／昏迷／不省人事／沒有?呼吸／沒有?心跳／大量出血／抽搐／胸痛／噎住／呼吸困難／意識不清／叫不醒)"}, {"code": "clinical", "pattern": "(診斷／病情／是不是(中風／骨折… | D | False | backend/app/services/qa_policy.py:56 |
| query.normalization | query | "def normalize_colloquial(question: str) -> str:\n    \"\"\"Keep every substantive clause, including clinical warning signs.\"\"\"\n    q = … | C | False | backend/app/services/query_understanding.py:28 |
| query.context | query | "def contextual_question(question: str, previous: str ／ None) -> str:\n    \"\"\"Only resolve an explicit administrative follow-up in the sa… | C | False | backend/app/services/query_understanding.py:35 |
| query.action_aliases | query | [["換藥", "更換敷料"], ["清傷口", "清潔傷口", "清洗傷口", "傷口清潔", "傷口簡易清潔"], ["餵食", "進食", "吃飯", "餵飯"], ["抽痰", "抽吸"], ["洗澡", "沐浴"], ["翻身", "變換姿勢"], ["回報", "通報… | C | False | backend/app/services/query_understanding.py:11 |
| query.expansion | query | "def _expand_query(question: str, today: date) -> str:\n    \"\"\"只用於檢索的保守查詢擴展，不改變使用者原始問題。\"\"\"\n    aliases: list[str] = []\n    aliases.e… | C | False | backend/app/services/retrieval.py:124 |
| query.intent_aliases | query | "def candidate_aliases(question: str) -> list[str]:\n    if care_reporting(question):\n        return ['異常事件', '身體不適', '通報', '回報', '第一線服務人員'… | C | False | backend/app/services/query_understanding.py:141 |
| answer.evidence_selection | answer | "def prioritize_admitted(question, admitted, chosen, top_k):\n    \"\"\"Reserve slots for fact-bearing admitted evidence, then other admitte… | C | False | backend/app/services/evidence_selection.py:49 |
| answer.validation | answer | "def node_verify(state: QaState) -> QaState:\n    \"\"\"驗證：引用存在、字面支持、輸出風險、跨文件衝突；LLM 自報只能多轉人工。\"\"\"\n    policy: QaPolicy = state[\"policy\"… | D | False | backend/app/services/qa_graph.py:431 |
| documents.eligibility | retrieval | "def current_versions(session: Session, org_id: uuid.UUID, facility_type: str, today: date) -> list[uuid.UUID]:\n    \"\"\"某機構在某日可用的現行版本 ID … | D | False | backend/app/services/documents.py:284 |
| prompt.version | answer | null | D | False | backend/app/providers/llm.py:101 |
| prompt.fingerprint | answer | "sha256:849a6f9ddc6ef486bfc62208dd13d62020a80139576cc6de1c93524480c1b52b" | D | False | backend/app/providers/llm.py:101 |
| policy.version | answer | "2026-10-09.medication-admin.1" | D | False | backend/app/services/qa_policy.py:39 |
| llm.options | answer | {"temperature": 0, "num_ctx": 6144, "num_predict": 400, "think": false, "format": "ANSWER_SCHEMA"} | B | False | backend/app/providers/llm.py:197 |

共 48 項。

可搜尋項需先具備 verified dataset、固定 KB snapshot 與隔離實驗環境。醫療風險、引用支持門檻、機構隔離、版本及 injection 防護維持安全約束；不得為提高回答率盲目放寬。
chunk 長度變更需要離線重新切塊／建立索引，不得在 production 就地覆寫；vector weight 從 lexical weight 派生，不能作獨立維度。

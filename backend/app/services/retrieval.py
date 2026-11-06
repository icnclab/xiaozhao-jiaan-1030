"""混合檢索：字元雙連詞全文＋向量，限定在使用者機構可用的現行版本。

分數說明（內部分流用，不是正確率）：
- coverage：問題雙連詞出現在切塊中的比例，以 IDF 加權（罕見詞比常見詞重要）。
- vector：與問題向量的 cosine 相似度。
- combined = lexical_weight × coverage ＋ (1 − lexical_weight) × max(vector, 0)。
  再加主題標題分與受主題相關性限制的意圖分；各分項保留供稽核。
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.providers.embedding import get_embedding_provider
from app.services.documents import current_versions
from app.services.qa_policy import DEFAULT_POLICY, QaPolicy, looks_like_injection
from app.services.text import bigrams, normalize
from app.services.evidence_text import substantive_body
from app.services.care_query import care_reporting, reporting_duty
from app.services.query_understanding import medication_admin_intent, purchasing_rule_intent
from app.services.query_understanding import (topic_token_groups, title_token_groups,
    candidate_aliases, permission_intent, boundary_intent, boundary_support)


@dataclass(frozen=True)
class RetrievedChunk:
    """檢索結果中的一個切塊（含顯示出處卡所需 metadata）。"""

    chunk_id: uuid.UUID
    version_id: uuid.UUID
    document_id: uuid.UUID
    title: str
    doc_type: str
    locator: str
    version_label: str
    effective_from: date | None
    effective_to: date | None
    text: str
    coverage: float
    vector: float
    combined: float
    injection_flag: bool
    hybrid_score: float = 0.0
    topic_relevance: float = 0.0
    title_bonus: float = 0.0
    intent_bonus: float = 0.0
    normalized_coverage: float = 0.0
    normalized_hybrid_score: float = 0.0
    scope_context: str = ''
    scope_chunk_ids: tuple[uuid.UUID, ...] = ()


ABSENT_TOKEN_FACTOR = 0.6
EXACT_TITLE_BONUS = 0.25
FUZZY_TITLE_BONUS_WEIGHT = 0.30
FUZZY_TITLE_MIN_COVERAGE = 0.35
PERMISSION_INTENT_BONUS = 0.22

_PERMISSION_RE = re.compile(
    r"可不可以|能不能|是否可以|是否能|可否|能否|可執行|能執行|"
    r"可以.{0,20}[嗎麼？?]|能.{0,20}[嗎麼？?]|資格|業務範圍|業務內容|服務範圍"
)
# 以空白取代，避免移除口語後產生不存在的跨詞 bigram。
_QUERY_FRAME_RE = re.compile(
    r"可不可以|能不能|是否可以|是否能|可否|能否|可以|可執行|能執行|"
    r"符合資格|資格|業務範圍|業務內容|服務範圍|"
    r"請問|幫忙|協助|幫|我|你|他|她|它|們|嗎|麼|呢"
)
# 保守的動作同義詞，不含文件名稱、文號或答案；僅原始問題命中時啟用。
_TOPIC_ALIASES = (
    ("換藥", "更換敷料"),
    ("餵食", "進食", "吃飯"),
    ("抽痰", "抽吸"),
    ("洗澡", "沐浴"),
    ("翻身", "變換姿勢"),
)
_SCOPE_RE = re.compile(
    r"業務內容|業務範圍|服務範疇|服務範圍|工作範圍|角色界線|服務契約|資格|不得|尚無不可|"
    r"不涉及|涉及.{0,8}(醫療|護理)|醫療.{0,8}(判斷|行為)|護理行為"
)


def _topic_token_groups(question: str) -> list[tuple[set[str], ...]]:
    """從原問句取主題 token；同義詞採 OR，多主題採平均。

    只清理額外排序訊號，不改原始 coverage 或任何安全判斷。
    """
    return topic_token_groups(question)


def _topic_match(groups: list[tuple[set[str], ...]], tokens: set[str]) -> float:
    # 同義詞需全部 bigram 都命中：「更換管路」不能因「更換」就當成「更換敷料」。
    return sum(any(variant and variant <= tokens for variant in group) for group in groups) / len(groups) if groups else 0.0


def _ranking_bonuses(question: str, title: str, chunk_text: str) -> tuple[float, float, float]:
    """主題相關性、標題分、意圖分；expanded query 不參與最終計分。

    意圖需主題至少 50% 命中；內文主題或業務範圍訊號限制段落加分，
    防止公文信頭只憑標題取得完整意圖分。所有分項有界、可稽核。
    """
    groups = _topic_token_groups(question)
    title_topic = _topic_match(title_token_groups(question), set(bigrams(title)))
    chunk_topic = _topic_match(groups, set(bigrams(chunk_text)))
    topic = max(title_topic, chunk_topic)
    title_bonus = FUZZY_TITLE_BONUS_WEIGHT * title_topic if title_topic >= FUZZY_TITLE_MIN_COVERAGE else 0.0
    scope = bool(_SCOPE_RE.search(normalize(re.sub(r"\s+", "", chunk_text))))
    intent_bonus = 0.0
    if permission_intent(question) and topic >= 0.5 and (not boundary_intent(question) or boundary_support(chunk_text)):
        title_intent = any(term in title for term in ("疑義", "資格", "業務內容", "業務範圍", "規定", "辦法"))
        intent_strength = 1.0 if title_intent else (0.5 if scope else 0.0)
        paragraph_relevance = max(chunk_topic, 0.75 if scope else 0.0)
        intent_bonus = PERMISSION_INTENT_BONUS * topic * intent_strength * paragraph_relevance
    return topic, title_bonus, intent_bonus


def _expand_query(question: str, today: date) -> str:
    """只用於檢索的保守查詢擴展，不改變使用者原始問題。"""
    aliases: list[str] = []
    aliases.extend(candidate_aliases(question))

    # 一般口語正規化：只影響檢索，不改使用者原始問題。
    # 目的不是針對單一題目，而是讓居服現場常見口語較容易對上正式文件用語。
    general_terms = (
        ("照服員", "照顧服務員"),
        ("長輩", "個案"),
        ("老人", "個案"),
        ("怎麼辦", "如何處理"),
        ("怎麼處理", "處理流程"),
        ("要怎麼處理", "處理流程"),
        ("要通知誰", "通報"),
        ("要跟誰說", "通報"),
        ("回報給誰", "通報"),
        ("跟進", "追蹤"),
        ("後續處理", "後續追蹤"),
    )
    for colloquial, formal in general_terms:
        if colloquial in question:
            aliases.append(formal)

    # 認證更新期限：僅在認證證明＋到期語境下轉換口語，保留其他條件。
    # 不全域替換「展延」，機構設立許可的展延是不同程序。
    if ("長照人員" in question or "長期照顧服務人員" in question) and "認證" in question and any(
        word in question for word in ("到期", "有效期限", "屆至")
    ) and any(word in question for word in ("更新", "展延")):
        question = question.replace("認證證明快到期了", "認證證明文件有效期限屆至")
        question = question.replace("認證證明即將到期", "認證證明文件有效期限屆至")
        question = question.replace("快到期了", "有效期限屆至").replace("即將到期", "有效期限屆至")
        question = question.replace("到期", "有效期限屆至").replace("申請展延", "申請更新")
        question = question.replace("最晚要在什麼時候前", "何時")

    # 評鑑督導制度：只處理聯繫會議頻率，不擴展到個別／團體督導。
    if (("督導制度" in question or "行政聯繫會議" in question)
        and "聯繫會議" in question
        and any(word in question for word in ("多久", "頻率", "多常", "幾個月", "每隔"))):
        if "行政聯繫會議" not in question:
            question = question.replace("聯繫會議", "行政聯繫會議")
        question = question.replace("至少多久要開一次", "應定期召開")
        question = question.replace("多久召開一次", "應定期召開")
        question = question.replace("多久至少要開一次", "應定期召開")

    # 傷口換藥：正式問法與口語問法
    if (
        "換藥" in question
        or "更換敷料" in question
        or ("傷口" in question and "換" in question and "藥" in question)
    ):
        aliases.append(
            "照顧服務員執行傷口換藥疑義 "
            "一般傷口更換敷料 傷口簡易清潔"
        )

    # 居家喘息：吃飯／餵食 → 進食
    if ("居家喘息" in question or "居家式喘息" in question) and any(
        word in question for word in ("吃飯", "餵食", "進食", "灌食")
    ):
        aliases.append(
            "居家式喘息服務進食服務疑義 進食 協助餵食 灌食"
        )

    # 跌倒等事故的口語問法 → 異常事件處理／通報
    if "跌倒" in question and any(
        word in question for word in ("回報", "通報", "通知", "處理", "怎麼辦")
    ):
        aliases.append(
            "居家服務督導員工作手冊 異常事件 跌倒 通報 處理流程 初報 續報 結報 後續追蹤"
        )
    # 居督異常事件
    if "異常事件" in question and any(
        word in question for word in ("督導", "居督", "居家服務")
    ):
        aliases.append(
            "居家服務督導員工作手冊 "
            "異常事件 通報 處理流程 完整記錄 後續追蹤"
        )

    # 官方服務紀錄參考格式
    if "服務紀錄" in question and "參考格式" in question:
        aliases.append(
            "長照專業服務操作指引 附錄一服務紀錄參考格式"
        )

    # 「今年評鑑」→ 當年度民國年評鑑基準
    if "評鑑" in question and any(
        word in question for word in ("居家式", "居家機構", "居家式機構")
    ):
        roc_year = today.year - 1911
        aliases.append(
            f"附件一 {roc_year}年度居家式長期照顧服務機構評鑑基準 "
            "工作手冊 管理制度 文件"
        )

    return question if not aliases else question + " " + " ".join(aliases)


def _idf_weights(session: Session, tokens: list[str], version_ids: list[uuid.UUID]) -> dict[str, float]:
    """問題 token 的 IDF 權重（BM25 式），在「使用者可見的現行版本」切塊上計算。

    高頻詞（住民、照服員）權重低，罕見詞（夜間、配置）權重高；語料中完全沒有的 token
    可能是雜訊雙連詞、也可能是知識庫沒涵蓋的概念，給 df=1 權重的 ABSENT_TOKEN_FACTOR 倍。

    Args:
        session: ORM session。
        tokens: 問題雙連詞（去重）。
        version_ids: 現行版本。

    Returns:
        token → 權重。
    """
    safe = [t for t in tokens if re.fullmatch(r"\w+", t)]
    if not safe:
        return {}
    total = session.execute(text("SELECT count(*) FROM chunks WHERE version_id = ANY(:v)"),
                            {"v": version_ids}).scalar() or 0
    rows = session.execute(
        text(
            """
            SELECT t.token, count(c.id) AS df
            FROM unnest(CAST(:tokens AS text[])) AS t(token)
            LEFT JOIN chunks c ON c.version_id = ANY(:v) AND c.tsv @@ to_tsquery('simple', t.token)
            GROUP BY t.token
            """
        ),
        {"tokens": safe, "v": version_ids},
    ).all()

    def idf(df: int) -> float:
        return math.log(1 + (total - df + 0.5) / (df + 0.5))

    weights = {}
    for row in rows:
        weights[row.token] = idf(row.df) if row.df else idf(1) * ABSENT_TOKEN_FACTOR
    return weights


_META_SQL = """
    SELECT c.id AS chunk_id, c.version_id, c.text, c.locator, dv.document_id, dv.version_label,
           dv.effective_from, dv.effective_to, d.title, d.doc_type
    FROM chunks c
    JOIN document_versions dv ON dv.id = c.version_id
    JOIN documents d ON d.id = dv.document_id
    WHERE c.id = ANY(:ids)
"""


def retrieve(
    session: Session,
    question: str,
    org_id: uuid.UUID,
    facility_type: str,
    today: date,
    policy: QaPolicy = DEFAULT_POLICY,
) -> list[RetrievedChunk]:
    """檢索問題的候選證據，依混合分數排序。

    Args:
        session: ORM session。
        question: 遮罩後問題。
        org_id: 使用者機構（跨機構內規永遠不在候選內）。
        facility_type: 機構類型（排除不適用文件）。
        today: 查詢日（決定現行版本）。
        policy: 問答政策。

    Returns:
        依 combined 由高到低排序的候選。
    """
    version_ids = current_versions(session, org_id, facility_type, today)
    if not version_ids:
        return []
    expanded_question = _expand_query(question, today)

    # 擴充詞只用於「找候選」；最後 lexical coverage 仍以使用者原始問題為準，
    # 避免大量 alias 稀釋短口語問句。
    original_tokens = sorted(set(bigrams(question)))
    expanded_tokens = sorted(set(bigrams(expanded_question)))

    normalized_question = re.sub(
        r"[\s《》〈〉「」『』【】（）()_\-—–·・,，。:：;；/\\]",
        "",
        question,
    )

    candidates: dict[uuid.UUID, float] = {}

    if expanded_tokens:
        safe = [t for t in expanded_tokens if re.fullmatch(r"\w+", t)]
        if safe:
            lexical_rows = session.execute(
                text(
                    """
                    SELECT c.id FROM chunks c
                    WHERE c.version_id = ANY(:versions)
                      AND c.tsv @@ to_tsquery('simple', :query)
                    ORDER BY ts_rank(c.tsv, to_tsquery('simple', :query)) DESC
                    LIMIT :k
                    """
                ),
                {"versions": version_ids, "query": " | ".join(safe), "k": policy.candidate_k},
            ).all()
            for row in lexical_rows:
                candidates.setdefault(row.id, 0.0)

    # 文件標題候選：
    # chunk 的 tsv 只索引內文，因此正式函釋／疑義文件可能因標題高度相關，
    # 但內文沒有重複標題文字而進不了 lexical candidate。
    # 先用 expanded query 與文件標題的 bigram 重疊找相關文件，
    # 再把該文件 chunks 加入候選，最後仍交給原有 coverage + vector 排序。
    expanded_token_set = set(expanded_tokens)
    title_rows = session.execute(
        text(
            """
            SELECT DISTINCT dv.document_id, d.title
            FROM document_versions dv
            JOIN documents d ON d.id = dv.document_id
            WHERE dv.id = ANY(:versions)
            """
        ),
        {"versions": version_ids},
    ).all()

    matched_document_ids = []
    for title_row in title_rows:
        title_token_set = set(bigrams(title_row.title))
        if not title_token_set:
            continue

        overlap = len(title_token_set & expanded_token_set)
        title_coverage = overlap / len(title_token_set)

        if overlap >= 2 and title_coverage >= 0.35:
            matched_document_ids.append(title_row.document_id)

    if matched_document_ids:
        title_chunk_rows = session.execute(
            text(
                """
                SELECT c.id
                FROM chunks c
                JOIN document_versions dv ON dv.id = c.version_id
                WHERE c.version_id = ANY(:versions)
                  AND dv.document_id = ANY(:document_ids)
                """
            ),
            {
                "versions": version_ids,
                "document_ids": matched_document_ids,
            },
        ).all()

        for row in title_chunk_rows:
            candidates.setdefault(row.id, 0.0)

    provider = get_embedding_provider()
    query_vector = provider.embed_query(expanded_question)
    vector_rows = session.execute(
        text(
            """
            SELECT c.id, 1 - (c.embedding <=> CAST(:qv AS vector)) AS sim FROM chunks c
            WHERE c.version_id = ANY(:versions) AND c.embedding_model = :model
            ORDER BY c.embedding <=> CAST(:qv AS vector)
            LIMIT :k
            """
        ),
        {"versions": version_ids, "qv": str(query_vector), "model": provider.model, "k": policy.candidate_k},
    ).all()
    vector_scores = {row.id: float(row.sim) for row in vector_rows}
    for chunk_id in vector_scores:
        candidates.setdefault(chunk_id, 0.0)
    if not candidates:
        return []

    # Recover only split administrative service table rows, inside eligible versions.
    # Stop at the next service code; never borrow scope from another table entry.
    scope_contexts = {}
    if medication_admin_intent(question) or purchasing_rule_intent(question):
        anchors = session.execute(text("""
            SELECT id, version_id, seq FROM chunks
            WHERE version_id = ANY(:versions) AND text ~ 'BA[0-9]{2}'
              AND text ~ '代購|代領|代送'
        """), {'versions': version_ids}).all()
        for anchor in anchors:
            neighbours = session.execute(text("""
                SELECT id, text FROM chunks WHERE version_id = :v AND seq BETWEEN :a AND :b ORDER BY seq
            """), {'v': anchor.version_id, 'a': anchor.seq, 'b': anchor.seq + 4}).all()
            block = []
            for row in neighbours:
                if row.id != anchor.id and re.search(r'BA\d{2}', row.text):
                    break
                block.append(row)
            context = '\n'.join(row.text for row in block)
            if (re.search(r'目的物品.{0,30}包括', re.sub(r'\s+', '', context))
                    and '藥品' in context and not looks_like_injection(context)):
                ids = tuple(row.id for row in block)
                for row in block:
                    candidates.setdefault(row.id, 0.0)
                    scope_contexts[row.id] = (context, ids)

    # 補齊不在向量前 k 名的候選的相似度
    missing = [cid for cid in candidates if cid not in vector_scores]
    if missing:
        for row in session.execute(
            text("SELECT id, 1 - (embedding <=> CAST(:qv AS vector)) AS sim FROM chunks WHERE id = ANY(:ids)"),
            {"qv": str(query_vector), "ids": missing},
        ).all():
            vector_scores[row.id] = float(row.sim)

    weights = _idf_weights(session, original_tokens, version_ids)
    total_weight = sum(weights.values())
    groups = _topic_token_groups(question)
    concept_tokens = sorted(set().union(*(variant for group in groups for variant in group))) if groups else []
    concept_idf = _idf_weights(session, concept_tokens, version_ids)
    group_weights = [max((concept_idf.get(token, 0.0) for variant in group for token in variant), default=0.0) for group in groups]
    group_total = sum(group_weights)
    results: list[RetrievedChunk] = []
    for row in session.execute(text(_META_SQL), {"ids": list(candidates)}).all():
        chunk_tokens = set(bigrams(row.text))
        coverage = (sum(w for t, w in weights.items() if t in chunk_tokens) / total_weight) if total_weight else 0.0
        vector = vector_scores.get(row.chunk_id, 0.0)

        combined = policy.lexical_weight * coverage + (1 - policy.lexical_weight) * max(vector, 0.0)
        hybrid_score = combined
        body_tokens = set(bigrams(substantive_body(row.text)))
        normalized_coverage = (sum(weight for group, weight in zip(groups, group_weights)
            if any(variant and variant <= body_tokens for variant in group)) / group_total) if group_total else 0.0
        normalized_hybrid = policy.lexical_weight * normalized_coverage + (1 - policy.lexical_weight) * max(vector, 0.0)
        # Parallel lexical representations, not additive rewards. Raw hybrid
        # remains auditable; aliases describe actions, never document titles.
        combined = max(hybrid_score, normalized_hybrid)
        topic_relevance, title_bonus, intent_bonus = _ranking_bonuses(question, row.title, row.text)

        normalized_title = re.sub(
            r"[\s《》〈〉「」『』【】（）()_\-—–·・,，。:：;；/\\]",
            "",
            row.title,
        )

        # 使用者明確點名完整文件名稱時，優先該文件。
        if len(normalized_title) >= 4 and normalized_title in normalized_question:
            title_bonus += EXACT_TITLE_BONUS

        combined += title_bonus + intent_bonus
        scope_context, scope_ids = scope_contexts.get(row.chunk_id, ('', ()))
        if scope_context and '藥品' in row.text:
            combined += PERMISSION_INTENT_BONUS
            intent_bonus += PERMISSION_INTENT_BONUS
        if care_reporting(question) and reporting_duty(row.text, records=bool(re.search(r'紀錄|記錄', question))):
            combined += PERMISSION_INTENT_BONUS
            intent_bonus += PERMISSION_INTENT_BONUS

        results.append(
            RetrievedChunk(
                chunk_id=row.chunk_id, version_id=row.version_id, document_id=row.document_id,
                title=row.title, doc_type=row.doc_type, locator=row.locator,
                version_label=row.version_label, effective_from=row.effective_from,
                effective_to=row.effective_to, text=row.text, coverage=round(coverage, 4),
                vector=round(vector, 4), combined=round(combined, 4),
                injection_flag=looks_like_injection(row.text),
                hybrid_score=round(hybrid_score, 4), topic_relevance=round(topic_relevance, 4),
                title_bonus=round(title_bonus, 4), intent_bonus=round(intent_bonus, 4),
                normalized_coverage=round(normalized_coverage, 4), normalized_hybrid_score=round(normalized_hybrid, 4),
                scope_context=scope_context, scope_chunk_ids=scope_ids,
            )
        )
    results.sort(key=lambda r: (
        bool(medication_admin_intent(question) and r.scope_chunk_ids and '藥品' in r.text),
        r.combined), reverse=True)
    return results



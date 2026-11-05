"""1030 嘉安訪談：依登入角色呈現高風險／不確定的安全訊息。

只處理 QA 回答文字；不改風險判斷、案件建立、通知及資料存取權限。
"""
from __future__ import annotations

URGENT_REASONS = frozenset({
    "risk_emergency",
    "risk_respiratory_abnormality",
    "risk_consciousness_abnormality",
    "risk_fall_head_impact",
    "risk_sudden_neurologic_abnormality",
    "risk_environmental_safety",
})


def make_role_aware(reason_code: str | None, user_role: str | None, base_message: str, *, question: str = "") -> str:
    """校正居督／主任提示語，安全事項仍依機構 SOP 及緊急救援流程。"""
    reason = (reason_code or "").strip()
    role = (user_role or "caregiver").strip().lower()
    original = (base_message or "").strip()
    is_risk = reason.startswith("risk_")
    urgent = reason in URGENT_REASONS
    # Distinguish a claimed confirmed death from an unresponsive person. We never
    # independently confirm death, prescribe medical intervention, or invent SOP.
    death_terms = ("死亡", "過世", "往生", "沒有生命跡象", "無生命跡象")
    death_question = reason == "risk_emergency" and any(term in question for term in death_terms)
    if death_question:
        suspected = any(term in question for term in ("疑似", "可能", "好像", "看起來", "不確定", "尚未確認", "無反應", "沒反應", "摸不到脈搏", "沒有呼吸"))
        if suspected:
            lead = ("目前不能依描述判定死亡。若當事人無反應或疑似沒有正常呼吸，"
                    "請立即撥打119並依緊急救護人員指示及機構應變流程處理，不要等待小照。")
        else:
            lead = ("小照無法核實死亡是否已由具權責的專業人員確認。"
                    "若仍有任何生命徵象疑慮或情況緊急，請立即撥打119。")
        if role in {"supervisor", "director", "admin"}:
            return (lead + "您目前是督導／主管角色，請即刻依機構核准的死亡事件及緊急應變SOP，"
                    "協調有權責的護理／醫療人員，完成必要通報與客觀紀錄；"
                    "在正式SOP與專業確認前，AI不提供死亡判定或法定程序結論。")
        return (lead + "請立即通知現場具權責人員及機構督導，"
                "客觀紀錄觀察到的情況；不要自行宣布死亡或等待AI案件回覆。")

    # 系統故障須忠實顯示原有錯誤訊息，不誤解為「查無依據」。
    if reason in {"llm_error", "llm_format", "internal_error"}:
        return original

    if role in {"supervisor", "director", "admin"}:
        if role == "supervisor":
            actor = "您目前是居督"
        elif role == "director":
            actor = "您目前是主任"
        else:
            actor = "您目前是管理角色"
        if is_risk:
            message = (
                f"{actor}。此問題涉及安全或專業判斷，請依機構現行緊急應變SOP啟動處理、"
                "協調具權責的人員並保留處置紀錄。AI無法取代現場評估或醫療專業判斷。"
            )
            if urgent:
                message += "若有人身立即危險，請優先撥打119（救護）或110（警察），不要等待系統回覆或案件接手。"
            return message
        # 不確定／引用不足仍交人工查核，不能回應「通知督導」，因為提問者可能就是居督。
        return (
            f"{actor}。目前無法依現有資料確認答案，請依機構SOP查核正式文件，"
            "必要時請具權責人員確認，勿將此結果視為已完成處置。"
        )

    if urgent:
        # 照服員沿用既有轉居督文字，額外把緊急求援置於明確可見處。
        return (
            "如有人身立即危險，請先依機構SOP求援並撥打119（救護）或110（警察），"
            "不要等待小照或居督回覆。\n" + original
        ).strip()
    return original

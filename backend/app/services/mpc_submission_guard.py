"""Server-side policy for explicit MPC -> ordinary case submission.

This validates the reviewed payload, not model-generated policy assertions.
The endpoint must still enforce authentication and organization permissions.
"""
from __future__ import annotations

import re

from app.services.mpc_handover import MpcPayloadError, build_review_draft


class MpcSubmissionBlocked(ValueError):
    pass


_CRITICAL = re.compile(
    r"(?:昏倒|叫不醒|無意識|無呼吸|沒呼吸|停止呼吸|無脈搏|大量出血|流血不止|"
    r"救命|失去意識|心跳停止|心肺停止|立即急救)"
)
_TECHNICAL = re.compile(
    r"跨輪解纏結重寫|FAMILY對CAREGIVER|CAREGIVER對SYSTEM|"
    r"OOD_PENDING_SOP|Thread_[0-9]+|\b(?:BA_22|GA09_SC09)\b"
)


def validated_ordinary_summary(payload: dict, review: dict) -> str:
    """Return a reviewed ordinary-case summary or refuse inappropriate MPC input."""
    try:
        draft = build_review_draft(payload, review)
    except (MpcPayloadError, TypeError, AttributeError, KeyError) as exc:
        raise MpcSubmissionBlocked("invalid_review_or_payload") from exc

    slot = payload.get("slot_state") or {}
    intents = payload.get("active_intents") or []
    flags = {str(s.get("safety_flag", "")).upper() for s in payload.get("segments", []) if isinstance(s, dict)}
    if (
        draft["emergency_candidate"]
        or str(payload.get("fsm_state", "")).startswith("SOS_")
        or "P0_Emergency_SOS" in intents
        or str(slot.get("service_domain", "")) == "SAFETY_EMERGENCY"
        or bool(flags & {"TIER1_SOS", "P0_EMERGENCY", "EMERGENCY"})
    ):
        raise MpcSubmissionBlocked("emergency_must_use_separate_response")

    # Independent content-level check: do not rely solely on upstream SAFE labels.
    texts = " ".join(str(s.get("masked_text", "")) for s in payload.get("segments", []) if isinstance(s, dict))
    if _CRITICAL.search(texts):
        raise MpcSubmissionBlocked("urgent_hazard_requires_emergency_triage")

    text = draft["reviewed_summary"].strip()
    if not text or len(text) > 1000:
        raise MpcSubmissionBlocked("summary_length_invalid")
    if _TECHNICAL.search(text):
        raise MpcSubmissionBlocked("technical_markup_not_allowed")
    return text

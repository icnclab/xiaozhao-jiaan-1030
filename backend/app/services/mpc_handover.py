"""MPC handover preview boundary. No persistence, notifications or automatic case creation.

The upstream MPC classification and speaker roles are predictions, not authority.
This module builds a reviewer-facing preview; actual confirmation must use the
existing authenticated transcript/case/emergency workflows.
"""
from __future__ import annotations

import re

STATES = {"Waiting_LINE_Confirm", "SOS_1_Alerting_All_Supervisors"}
ALLOWED_ROLES = {"CAREGIVER", "SUPERVISOR", "FAMILY", "ELDER", "SYSTEM", "O", "UNKNOWN"}
INTENTS = {"QA_RAG_Query", "Case_Report", "OOD_Escalate_Supervisor", "P0_Emergency_SOS"}
RISK_FLAGS = {"TIER1_SOS", "TIER2_MED_RISK", "HARASSMENT_RISK"}


class MpcPayloadError(ValueError):
    pass


def _string(value, label, maxlen=1500):
    if not isinstance(value, str) or not value.strip() or len(value) > maxlen:
        raise MpcPayloadError(f"invalid_{label}")
    return value.strip()


def _role(value):
    # Roles may contain UI hints, e.g. FAMILY (system suggested), never trust them.
    head = str(value).split(' ', 1)[0].upper()
    return head if head in ALLOWED_ROLES else 'UNKNOWN'


def build_preview(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise MpcPayloadError('payload_must_be_object')
    event = _string(payload.get('client_event_id'), 'client_event_id', 128)
    if not re.fullmatch(r'[A-Za-z0-9_-]+', event):
        raise MpcPayloadError('invalid_event_id_chars')
    state = _string(payload.get('fsm_state'), 'fsm_state', 80)
    if state not in STATES:
        raise MpcPayloadError('unsupported_state')
    segments = payload.get('segments')
    if not isinstance(segments, list) or not 1 <= len(segments) <= 100:
        raise MpcPayloadError('invalid_segments')
    seen, safe_segments = set(), []
    for seg in segments:
        if not isinstance(seg, dict) or type(seg.get('idx')) is not int or seg['idx'] < 0 or seg['idx'] in seen:
            raise MpcPayloadError('invalid_segment_index')
        seen.add(seg['idx'])
        text = _string(seg.get('masked_text'), 'masked_text', 2000)
        flag = str(seg.get('safety_flag', 'UNKNOWN')).upper()
        safe_segments.append({'idx': seg['idx'], 'masked_text': text,
                              'predicted_role': _role(seg.get('predicted_role','UNKNOWN')),
                              'safety_flag': flag[:40]})
    selected = payload.get('selected_idx')
    if not isinstance(selected, list) or not selected or any(type(i) is not int or i not in seen for i in selected) or len(set(selected)) != len(selected):
        raise MpcPayloadError('selected_idx_invalid')
    summary = _string(payload.get('summary'), 'summary', 3000)
    slot = payload.get('slot_state')
    if not isinstance(slot, dict):
        raise MpcPayloadError('slot_state_required')
    intents = payload.get('active_intents')
    if not isinstance(intents, list) or any(not isinstance(i, str) or i not in INTENTS for i in intents):
        raise MpcPayloadError('invalid_intents')
    draft = payload.get('work_summary_draft')
    if not isinstance(draft, dict):
        raise MpcPayloadError('work_summary_draft_required')
    roles = payload.get('roles')
    if not isinstance(roles, dict) or len(roles)>100:
        raise MpcPayloadError('roles_required')
    is_p0 = ('P0_Emergency_SOS' in intents or state.startswith('SOS_') or
             any(s['safety_flag']=='TIER1_SOS' for s in safe_segments))
    if is_p0 and ('P0_Emergency_SOS' not in intents or not state.startswith('SOS_')):
        raise MpcPayloadError('inconsistent_p0_state_intents')
    needs_safety_review = (is_p0 or any(s['safety_flag'] in RISK_FLAGS for s in safe_segments) or
                           'OOD_Escalate_Supervisor' in intents)
    # Defensive check: a model SAFE label cannot override physical hazard cues.
    warning_terms = ('淹水', '咬人狗', '咬人犬', '犬隻', '性騷擾', '摸大腿', '昏倒', '叫不醒', '普拿疼', '買藥', '用藥')
    if any(w in ' '.join(s['masked_text'] for s in safe_segments) for w in warning_terms):
        needs_safety_review = True
    return {
        'client_event_id': event,
        'fsm_state': state,
        'selected_idx': selected,
        'selected_segments': [s for s in safe_segments if s['idx'] in selected],
        'speaker_role_suggestions': {str(k)[:40]: _role(v) for k,v in roles.items()},
        'summary_suggestion': summary,
        'active_intents': intents,
        'slot_state_suggestion': slot,
        'work_summary_draft_suggestion': draft,
        'requires_human_confirmation': True,
        'requires_safety_review': needs_safety_review,
        'emergency_candidate': is_p0,
        'saved': False,
        'case_created': False,
        'notification_sent': False,
        'warnings': [
            'Source roles, masks, categories and medical/legal judgments are model guesses; review before using.',
            'No automatic case, emergency, approved service form or push notification is created.',
            'For urgent danger call emergency services and follow approved procedures; do not await this preview.',
        ],
    }


# Stateless, human-reviewed draft. This is deliberately NOT a persistence or send endpoint.
def build_review_draft(payload: dict, review: dict) -> dict:
    base = build_preview(payload)
    if not isinstance(review, dict) or review.get('acknowledge_review') is not True:
        raise MpcPayloadError('explicit_review_acknowledgement_required')
    selected = review.get('selected_idx')
    original_indices = {s['idx'] for s in base['selected_segments']}
    # The reviewer can remove irrelevant clips but cannot add unseen clips here.
    if not isinstance(selected, list) or not selected or len(set(map(str,selected))) != len(selected) or any(type(i) is not int or i not in original_indices for i in selected):
        raise MpcPayloadError('review_selected_idx_invalid')
    role_fixes = review.get('role_corrections', {})
    if not isinstance(role_fixes, dict) or len(role_fixes) > 100:
        raise MpcPayloadError('invalid_role_corrections')
    known_speakers = set(base['speaker_role_suggestions'])
    if any(not isinstance(k,str) or k not in known_speakers or not isinstance(v,str) or v.upper() not in ALLOWED_ROLES for k,v in role_fixes.items()):
        raise MpcPayloadError('unknown_speaker_or_role')
    confirmed_summary = _string(review.get('confirmed_summary'), 'confirmed_summary', 3000)
    if '<script' in confirmed_summary.lower():
        raise MpcPayloadError('unsafe_summary_markup')
    reviewed_roles = dict(base['speaker_role_suggestions'])
    reviewed_roles.update({k:v.upper() for k,v in role_fixes.items()})
    selected_segments = [s for s in base['selected_segments'] if s['idx'] in selected]
    # Do not trust SAFE claims made by MPC, including after reviewer changes.
    return {
        'client_event_id': base['client_event_id'],
        'selected_idx': selected,
        'selected_segments': selected_segments,
        'reviewed_roles': reviewed_roles,
        'reviewed_summary': confirmed_summary,
        'suggested_service_domain': str(base['slot_state_suggestion'].get('service_domain', 'UNKNOWN'))[:80],
        'suggested_service_code': str(base['slot_state_suggestion'].get('service_code', 'UNKNOWN'))[:80],
        'suggested_report_categories': base['slot_state_suggestion'].get('report_categories', []),
        'requires_supervisor_review': base['requires_safety_review'] or base['emergency_candidate'],
        'emergency_candidate': base['emergency_candidate'],
        'reviewed_by_authenticated_user': True,
        'review_only': True,
        'saved': False, 'case_created': False, 'notification_sent': False,
        'notice': 'Preview only. Confirmed drafts do not create records, emergencies, or notifications. Explicit submission and server-side authorization are required in a later workflow.'
    }

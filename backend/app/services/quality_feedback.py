"""Isolated collector/review/export; no QA, case, notification writes."""
import csv
import io
import json
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chunk, Organization, QaItem, User
from app.quality_models import QualityFeedback, QualityReview
from app.services import audit
from app.services.deid import deidentify
from app.services.qa_service import load_deid_terms
from app.services.quality_trace import historical

Behavior = Literal['answer','refuse','clarify','escalate','risk_block','direct_answer','concise_answer']
ErrorType = Literal['wrong_answer','incomplete_answer','false_refusal','unsafe_answer','retrieval_miss',
                    'wrong_source','insufficient_evidence','risk_false_negative','risk_false_positive',
                    'wrong_escalation','other','repetitive_answer','verbose_answer','duplicate_citation']


class Correction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    error_type: ErrorType
    expected_behavior: Behavior
    correct_answer: str = Field(default='', max_length=6000)
    correct_source_document: str = Field(default='', max_length=500)
    correct_source_page_or_section: str = Field(default='', max_length=500)
    evidence_summary: str = Field(default='', max_length=6000)
    notes: str = Field(default='', max_length=3000)


EvidenceBasis = Literal['official_kb_document','system_safety_policy','institution_policy','expert_review','pending_evidence']

class ReviewIn(Correction):
    evidence_basis_type: EvidenceBasis | None = None
    policy_identifier: str = Field(default='', max_length=500)
    policy_version: str = Field(default='', max_length=500)
    institution_identifier: str = Field(default='', max_length=500)
    institution_rule_identifier: str = Field(default='', max_length=500)
    expert_review_record: str = Field(default='', max_length=6000)
    complete_answer_confirmed: bool = False
    data_quality_checked: bool = False
    data_quality_conflicts: str = Field(default='', max_length=3000)
    status: Literal['pending_review','verified','rejected']
    expected_revision: int = Field(ge=0)
    evidence_checked: bool = False
    reviewer_notes: str = Field(default='', max_length=3000)


def error(code, message, status=422):
    return HTTPException(status, detail={'code':code,'message':message})


def clean(db, user, body):
    terms = load_deid_terms(db, user.org_id)
    return {k: deidentify(v, terms).text if isinstance(v, str) else v
            for k, v in body.model_dump().items()}


def snapshot(db, item, user):
    from app.api.serializers import citations_out
    institution = db.get(Organization, item.org_id)
    owner = db.get(User, item.user_id)
    sources = citations_out(db, item.id)
    for source in sources:
        chunk = db.get(Chunk, uuid.UUID(source['chunk_id']))
        if chunk: source['text'] = chunk.text
    now = datetime.now(timezone.utc).isoformat()
    trace = historical(item)
    return dict(qa_id=str(item.id), question=item.question_masked, ai_answer=item.answer_text,
                sources=sources, user_id=str(item.user_id), user_role=owner.role,
                submitted_by=str(user.id), submitted_role=user.role,
                institution={'id':str(institution.id),'code':institution.code,'name':institution.name},
                timestamp=now, qa_timestamp=item.created_at.isoformat(),
                rag_version=trace.get('rag_version'), qa_policy_version=item.qa_policy_version,
                prompt_version=trace.get('prompt_version'), runtime=trace)


def submit(db: Session, item: QaItem, user: User, body: Correction):
    # Tenant lock serializes concurrent submissions against the same original QA.
    db.scalar(select(QaItem).where(QaItem.id==item.id).with_for_update())
    row = db.scalar(select(QualityFeedback).where(QualityFeedback.qa_id==item.id,
                                                 QualityFeedback.submitted_by==user.id))
    if row is not None:
        return row  # retry is idempotent; immutable submission is not overwritten
    row = QualityFeedback(org_id=item.org_id, qa_id=item.id, submitted_by=user.id,
                          qa_snapshot=snapshot(db,item,user), submission=clean(db,user,body))
    db.add(row)
    db.flush()
    audit.record(db,'quality.feedback.submit',actor=user,target_type='quality_feedback',target_id=row.id)
    db.commit()
    return row


GENERAL_FIELDS = set(Correction.model_fields) | {'reviewer_notes'}
GOLD_FIELDS = set(ReviewIn.model_fields) - GENERAL_FIELDS - {'status','expected_revision'}
NO_CONFLICT = {'', '無', '沒有', 'none', 'n/a', 'na', '不適用'}

def normalize_conflicts(value):
    value = str(value or '').strip()
    return '' if value.casefold() in NO_CONFLICT else value

def approval_fingerprint(correction):
    import hashlib
    keys = GENERAL_FIELDS | GOLD_FIELDS
    payload = {k: correction.get(k) for k in sorted(keys)}
    payload['data_quality_conflicts'] = normalize_conflicts(payload.get('data_quality_conflicts'))
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def review(db: Session, row: QualityFeedback, user: User, body: ReviewIn):
    if user.role not in ('admin','supervisor') or row.org_id != user.org_id:
        raise error('forbidden','無權限審核此回饋',403)
    admin = user.role == 'admin'
    if not admin and body.model_fields_set & GOLD_FIELDS:
        raise error('gold_admin_only','Gold 資料欄位僅限管理員修改',403)
    if row.revision != body.expected_revision:
        raise error('stale_review','回饋已被其他審核者修改，請重新載入',409)
    if body.status == 'verified':
        if row.submitted_by == user.id:
            raise error('self_verification','請由另一位 admin／supervisor 核對此回饋',403)
        required = ['evidence_summary']
        basis = body.evidence_basis_type if admin else None
        if basis == 'official_kb_document' or (basis is None and body.expected_behavior in ('answer','direct_answer','concise_answer')):
            required += ['correct_answer','correct_source_document','correct_source_page_or_section']
        if basis == 'system_safety_policy': required += ['policy_identifier','policy_version']
        elif basis == 'institution_policy': required += ['institution_identifier','institution_rule_identifier']
        elif basis == 'expert_review': required += ['expert_review_record']
        if (admin and not body.evidence_checked) or any(not getattr(body,k).strip() for k in required):
            raise error('evidence_required','驗證前請填妥修正與依據；Gold 確認由管理員處理')
    cleaned = clean(db,user,body)
    correction = dict(row.reviewed_correction or {})
    allowed = GENERAL_FIELDS | GOLD_FIELDS if admin else GENERAL_FIELDS
    correction.update({k:v for k,v in cleaned.items() if k in allowed})
    if admin:
        correction['data_quality_conflicts'] = normalize_conflicts(correction.get('data_quality_conflicts'))
        correction['gold_approved_by'] = str(user.id) if body.status == 'verified' else None
        correction['gold_approved_at'] = datetime.now(timezone.utc).isoformat()
        correction['gold_approval_fingerprint'] = approval_fingerprint(correction)
    correction['general_review_reopens_gold'] = not admin and (bool((row.reviewed_correction or {}).get('general_review_reopens_gold')) or row.status != body.status or correction != (row.reviewed_correction or {}))
    row.revision += 1
    row.status = body.status
    row.reviewed_correction = correction
    row.reviewed_by = user.id
    row.reviewed_at = datetime.now(timezone.utc)
    db.add(QualityReview(feedback_id=row.id,org_id=row.org_id,reviewer_id=user.id,
                        revision=row.revision,decision=row.status,correction=correction))
    audit.record(db,'quality.feedback.review',actor=user,target_type='quality_feedback',target_id=row.id,
                 meta={'revision':row.revision,'decision':row.status})
    db.commit()
    return row


def gold_readiness(row):
    """Derived eligibility, never backfills submission or changes review status."""
    c = row.reviewed_correction or {}
    reasons = []
    if row.status != 'verified' or c.get('evidence_basis_type') == 'pending_evidence':
        return {'state':'not_eligible','reasons':['not_verified' if row.status != 'verified' else 'pending_evidence']}
    basis = c.get('evidence_basis_type')
    required = ['correct_answer','evidence_summary']
    if basis == 'official_kb_document': required += ['correct_source_document','correct_source_page_or_section']
    elif basis == 'system_safety_policy': required += ['policy_identifier','policy_version']
    elif basis == 'institution_policy': required += ['institution_identifier','institution_rule_identifier']
    elif basis == 'expert_review':
        required += ['expert_review_record']
        if not row.reviewed_by or not row.reviewed_at: reasons.append('expert_review_provenance_missing')
    else: reasons.append('evidence_basis_missing')
    placeholders = {'', '不適用', '待補', '待補依據', '未記錄', 'n/a', 'none'}
    reasons += [f'missing_{key}' for key in required
                if str(c.get(key) or '').strip().lower() in placeholders]
    if c.get('expected_behavior') not in Behavior.__args__: reasons.append('invalid_behavior')
    if c.get('error_type') not in ErrorType.__args__: reasons.append('invalid_error_type')
    if c.get('error_type') == 'risk_false_positive' and c.get('expected_behavior') == 'risk_block': reasons.append('label_behavior_conflict')
    if c.get('error_type') == 'risk_false_negative' and c.get('expected_behavior') != 'risk_block': reasons.append('label_behavior_conflict')
    if c.get('error_type') == 'false_refusal' and c.get('expected_behavior') == 'refuse': reasons.append('label_behavior_conflict')
    if not c.get('complete_answer_confirmed'): reasons.append('answer_completeness_unconfirmed')
    if not c.get('data_quality_checked'): reasons.append('quality_review_unconfirmed')
    if not c.get('evidence_checked'): reasons.append('evidence_unchecked')
    if normalize_conflicts(c.get('data_quality_conflicts')): reasons.append('data_quality_conflict')
    # Human attestation is required: a nonempty string is not proof of completeness.
    import re
    if re.match(r'^(?:保留核心內容|(?:請)?(?:刪掉|刪除|移除)重複)', str(c.get('correct_answer') or '').strip()):
        reasons.append('answer_is_editing_instruction')
    if c.get('general_review_reopens_gold') or not c.get('gold_approved_by') or not c.get('gold_approved_at') or c.get('gold_approval_fingerprint') != approval_fingerprint(c): reasons.append('admin_gold_confirmation_required')
    return {'state':'needs_review' if reasons else 'ready','reasons':reasons}


def gold_priority(row):
    c = row.reviewed_correction or row.submission or {}
    reasons = gold_readiness(row)['reasons']
    if c.get('error_type') in ('risk_false_negative','risk_false_positive','unsafe_answer') or 'label_behavior_conflict' in reasons: return 'P0 安全'
    if any(r.startswith('missing_') or r in ('answer_completeness_unconfirmed','answer_is_editing_instruction','evidence_basis_missing','expert_review_provenance_missing','evidence_unchecked','data_quality_conflict') for r in reasons): return 'P1 資料品質'
    if c.get('error_type') in ('false_refusal','retrieval_miss','wrong_source'): return 'P2 檢索'
    return 'P3 回答品質'


def out(row, user=None):
    result = dict(gold_priority=gold_priority(row),gold_readiness=gold_readiness(row)['state'],gold_readiness_details=gold_readiness(row),id=str(row.id),qa_id=str(row.qa_id),status=row.status,revision=row.revision,
                qa_snapshot=row.qa_snapshot,submission=row.submission,
                reviewed_correction=row.reviewed_correction,dataset_split=row.dataset_split,
                submitted_by=str(row.submitted_by),reviewed_by=str(row.reviewed_by) if row.reviewed_by else None,
                reviewed_at=row.reviewed_at.isoformat() if row.reviewed_at else None,
                created_at=row.created_at.isoformat())

    if user is not None and user.role != 'admin':
        snapshot = dict(result['qa_snapshot'])
        runtime = snapshot.get('runtime') or {}
        snapshot['runtime'] = {k:runtime.get(k) for k in ('risk_gate_result','escalation_result')}
        for key in ('rag_version','qa_policy_version','prompt_version'): snapshot.pop(key,None)
        result['qa_snapshot'] = snapshot
        result.pop('gold_readiness_details',None)
    return result


def review_history(db, row):
    return [dict(revision=r.revision,decision=r.decision,reviewer_id=str(r.reviewer_id),
                 correction=r.correction,created_at=r.created_at.isoformat())
            for r in db.scalars(select(QualityReview).where(QualityReview.feedback_id==row.id,
                                                          QualityReview.org_id==row.org_id)
                                .order_by(QualityReview.revision))]


def export_records(db, user, *, gold=False):
    if gold and user.role != "admin": raise error("gold_admin_only","Gold 匯出僅限管理員",403)
    rows = db.scalars(select(QualityFeedback).where(QualityFeedback.org_id==user.org_id,
                                                   QualityFeedback.status=='verified')
                      .order_by(QualityFeedback.created_at,QualityFeedback.id)).all()
    if gold: rows = [r for r in rows if gold_readiness(r)['state'] == 'ready']
    records = [dict(schema_version=1, **out(r,user), review_history=review_history(db,r)) for r in rows]
    audit.record(db,'quality.dataset.gold_export' if gold else 'quality.dataset.export',actor=user,target_type='quality_dataset',
                 meta={'verified_count':len(records)})
    db.commit()
    return records


def encode_export(records, format):
    if format == 'json':
        return json.dumps({'schema_version':1,'count':len(records),'records':records},ensure_ascii=False,indent=2)
    if format == 'jsonl':
        return ''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records)
    fields=['id','qa_id','status','revision','dataset_split','qa_snapshot','submission',
            'gold_readiness','gold_readiness_details','reviewed_correction','reviewed_by','reviewed_at','review_history','created_at','schema_version']
    buffer=io.StringIO()
    writer=csv.DictWriter(buffer,fieldnames=fields,extrasaction='ignore')
    writer.writeheader()
    for r in records:
        values={k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()}
        # Prevent spreadsheet formulas from user-provided exported strings.
        values={k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in values.items()}
        writer.writerow(values)
    return '\ufeff'+buffer.getvalue()

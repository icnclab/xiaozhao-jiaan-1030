"""Gold dataset eligibility regression; no production DB writes."""
import sys, json, csv, io, unittest, uuid
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pydantic import ValidationError
from fastapi import HTTPException
from app.services.quality_feedback import ReviewIn, Correction, gold_readiness, approval_fingerprint, export_records, encode_export, review

ORG=uuid.uuid4()

def row(**changes):
    correction=dict(error_type='wrong_answer',expected_behavior='answer',correct_answer='完整參考答案。',
      evidence_basis_type='official_kb_document',correct_source_document='原文文件',correct_source_page_or_section='第1頁',evidence_summary='實際依據摘要',
      evidence_checked=True,complete_answer_confirmed=True,data_quality_checked=True)
    correction.update(changes)
    correction.update(gold_approved_by="admin",gold_approved_at="now",gold_approval_fingerprint=approval_fingerprint(correction))
    now=datetime.now(timezone.utc)
    return SimpleNamespace(org_id=ORG,id=uuid.uuid4(),qa_id=uuid.uuid4(),status='verified',revision=1,reviewed_correction=correction,
      reviewed_by=uuid.uuid4(),reviewed_at=now,submission={'original':'immutable'},qa_snapshot={},dataset_split=None,submitted_by=uuid.uuid4(),created_at=now)
class GoldTests(unittest.TestCase):
    def test_legacy_is_not_auto_gold(self):
        r=row();r.reviewed_correction={'error_type':'wrong_answer','expected_behavior':'answer','correct_answer':'答案'}
        self.assertEqual(gold_readiness(r)['state'],'needs_review')
    def test_official_document_requirements(self):
        self.assertEqual(gold_readiness(row())['state'],'ready')
        for key in ['correct_source_document','correct_source_page_or_section','evidence_summary','correct_answer']:
            self.assertEqual(gold_readiness(row(**{key:''}))['state'],'needs_review')
    def test_policy_needs_version_not_pdf(self):
        r=row(evidence_basis_type='system_safety_policy',policy_identifier='safe',policy_version='v1',correct_source_document='',correct_source_page_or_section='')
        self.assertEqual(gold_readiness(r)['state'],'ready')
        r.reviewed_correction['policy_version']='';self.assertEqual(gold_readiness(r)['state'],'needs_review')
    def test_institution_and_expert_provenance(self):
        self.assertEqual(gold_readiness(row(evidence_basis_type='institution_policy',institution_identifier='institution',institution_rule_identifier='rule-v1'))['state'],'ready')
        self.assertEqual(gold_readiness(row(evidence_basis_type='institution_policy'))['state'],'needs_review')
        r=row(evidence_basis_type='expert_review',expert_review_record='覆核紀錄');self.assertEqual(gold_readiness(r)['state'],'ready')
        r.reviewed_by=None;self.assertEqual(gold_readiness(r)['state'],'needs_review')
    def test_pending_and_rejected_are_ineligible(self):
        self.assertEqual(gold_readiness(row(evidence_basis_type='pending_evidence'))['state'],'not_eligible')
        for status in ['pending_review','rejected']:
            r=row();r.status=status;self.assertEqual(gold_readiness(r)['state'],'not_eligible')
    def test_conflicts_and_completeness(self):
        for change in [dict(error_type='risk_false_positive',expected_behavior='risk_block'),dict(error_type='risk_false_negative',expected_behavior='answer'),dict(data_quality_conflicts='待裁定'),dict(correct_answer='保留核心內容，但刪掉重複'),dict(complete_answer_confirmed=False),dict(data_quality_checked=False),dict(expected_behavior='invalid')]:
            self.assertEqual(gold_readiness(row(**change))['state'],'needs_review')
    def test_typed_basis_validated_on_verification(self):
        for basis in ['official_kb_document','system_safety_policy','institution_policy','expert_review']:
            body=ReviewIn(error_type='wrong_answer',expected_behavior='answer',correct_answer='答案',evidence_summary='摘要',evidence_checked=True,evidence_basis_type=basis,status='verified',expected_revision=1)
            with self.assertRaises(HTTPException):review(None,row(),SimpleNamespace(id=uuid.uuid4(),role="admin",org_id=ORG),body)
    def test_invalid_basis_and_legacy_input(self):
        self.assertIsNone(ReviewIn(error_type='wrong_answer',expected_behavior='answer',status='pending_review',expected_revision=0).evidence_basis_type)
        with self.assertRaises(ValidationError):ReviewIn(error_type='wrong_answer',expected_behavior='answer',status='pending_review',expected_revision=0,evidence_basis_type='invented')
        self.assertNotIn('evidence_basis_type',Correction(error_type='wrong_answer',expected_behavior='answer').model_dump())
    def test_review_preserves_original_and_appends_history(self):
        r=row(); original=dict(r.submission); added=[]
        db=SimpleNamespace(add=added.append,commit=lambda:None)
        body=ReviewIn(error_type='wrong_answer',expected_behavior='answer',correct_answer='完整新答案。',evidence_basis_type='system_safety_policy',policy_identifier='safe',policy_version='v2',evidence_summary='安全界線依據',evidence_checked=True,complete_answer_confirmed=True,data_quality_checked=True,status='verified',expected_revision=1)
        with patch('app.services.quality_feedback.clean',side_effect=lambda db,u,b:b.model_dump()),patch('app.services.quality_feedback.audit.record'):
            review(db,r,SimpleNamespace(id=uuid.uuid4(),role="admin",org_id=ORG),body)
        self.assertEqual(r.submission,original)
        self.assertEqual(r.revision,2);self.assertEqual(len(added),1)
        self.assertEqual(added[0].revision,2);self.assertEqual(added[0].correction['policy_version'],'v2')
        self.assertEqual(gold_readiness(r)['state'],'ready')
    def test_placeholders_do_not_make_ready(self):
        self.assertEqual(gold_readiness(row(correct_source_page_or_section='不適用'))['state'],'needs_review')
        self.assertEqual(gold_readiness(row(error_type='false_refusal',expected_behavior='refuse'))['state'],'needs_review')
    def test_gold_filter_and_all_formats(self):
        ready=row();pending=row(evidence_basis_type='pending_evidence');needs=row(complete_answer_confirmed=False)
        db=SimpleNamespace(scalars=lambda q:SimpleNamespace(all=lambda:[ready,pending,needs]),commit=lambda:None)
        with patch('app.services.quality_feedback.audit.record'),patch('app.services.quality_feedback.review_history',return_value=[]):
            self.assertEqual(len(export_records(db,SimpleNamespace(org_id=ORG,role="admin"))),3)
            records=export_records(db,SimpleNamespace(org_id=ORG,role="admin"),gold=True)
        self.assertEqual(len(records),1)
        self.assertEqual(json.loads(encode_export(records,'json'))['records'][0]['gold_readiness'],'ready')
        self.assertEqual(json.loads(encode_export(records,'jsonl'))['reviewed_correction']['evidence_basis_type'],'official_kb_document')
        self.assertEqual(next(csv.DictReader(io.StringIO(encode_export(records,'csv').lstrip('\ufeff'))))['gold_readiness'],'ready')
if __name__=='__main__':unittest.main(verbosity=2)

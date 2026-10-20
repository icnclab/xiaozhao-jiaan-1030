"""Feedback enums/export compatibility; no database writes."""
import csv
import io
import json
import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import get_args

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from pydantic import ValidationError
from app.services.quality_feedback import Behavior, ErrorType, Correction, ReviewIn, encode_export, review


ORG=uuid.uuid4()

class FeedbackOptions(unittest.TestCase):
    def test_legacy_codes_remain_valid_without_conversion(self):
        errors=['wrong_answer','incomplete_answer','false_refusal','unsafe_answer','retrieval_miss',
                'wrong_source','insufficient_evidence','risk_false_negative','risk_false_positive','wrong_escalation','other']
        for error in errors:
            for behavior in ['answer','refuse','clarify','escalate','risk_block']:
                with self.subTest(error=error,behavior=behavior):
                    data=Correction(error_type=error,expected_behavior=behavior).model_dump()
                    self.assertEqual((data['error_type'],data['expected_behavior']),(error,behavior))

    def test_new_codes_validate_and_export_all_formats_unchanged(self):
        for error in ['repetitive_answer','incomplete_answer','verbose_answer','duplicate_citation']:
            for behavior in ['direct_answer','concise_answer']:
                with self.subTest(error=error,behavior=behavior):
                    value=ReviewIn(error_type=error,expected_behavior=behavior,status='verified',expected_revision=0,
                                   correct_answer='修正答案',correct_source_document='文件',
                                   correct_source_page_or_section='第1頁',evidence_summary='原文',evidence_checked=True)
                    record={'id':'fixture','status':'verified','reviewed_correction':value.model_dump()}
                    records=json.loads(encode_export([record],'json'))['records']
                    line=json.loads(encode_export([record],'jsonl'))
                    row=next(csv.DictReader(io.StringIO(encode_export([record],'csv').lstrip('\ufeff'))))
                    for exported in [records[0]['reviewed_correction'],line['reviewed_correction'],json.loads(row['reviewed_correction'])]:
                        self.assertEqual((exported['error_type'],exported['expected_behavior']),(error,behavior))

    def test_new_answer_behaviors_cannot_bypass_source_validation(self):
        for behavior in ['direct_answer','concise_answer']:
            with self.subTest(behavior=behavior),self.assertRaises(HTTPException) as cm:
                review(None,SimpleNamespace(org_id=ORG,revision=0,submitted_by=uuid.uuid4()),SimpleNamespace(id=uuid.uuid4(),org_id=ORG,role="admin"),
                       ReviewIn(error_type='verbose_answer',expected_behavior=behavior,status='verified',
                                expected_revision=0,evidence_summary='摘要',evidence_checked=True))
            self.assertEqual(cm.exception.status_code,422)

    def test_invalid_codes_rejected(self):
        with self.assertRaises(ValidationError):Correction(error_type='unknown',expected_behavior='answer')
        with self.assertRaises(ValidationError):Correction(error_type='wrong_answer',expected_behavior='unknown')

    def test_frontend_backend_options_match(self):
        import re
        source=(Path(__file__).resolve().parents[2]/'frontend/src/quality/FeedbackFields.tsx').read_text(encoding='utf-8')
        errors,behaviors=source.split('export const BEHAVIORS',1)
        self.assertEqual(set(re.findall(r'\["([a-z_]+)",',errors)),set(get_args(ErrorType)))
        self.assertEqual(set(re.findall(r'\["([a-z_]+)",',behaviors.split('export interface',1)[0])),set(get_args(Behavior)))


if __name__=='__main__':unittest.main(verbosity=2)

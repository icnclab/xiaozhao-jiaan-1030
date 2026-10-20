"""Freeze reviewed Gold through existing admin Gold export API handler.

The existing endpoint writes only its normal export audit. Dataset and review
history are fingerprinted before/after. No QA, cases, reviews or splits written.
"""
import csv
import hashlib
import io
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, select, or_, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.config import get_settings
from app.models import Organization, User, Document, DocumentVersion
from app.quality_models import QualityFeedback, QualityReview
from app.services.quality_feedback import gold_readiness, out, review_history
from app.services.quality_trace import versions
from app.services.qa_policy import DEFAULT_POLICY
from app.api.quality_routes import export_gold, gold_stats

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'quality_tests/v1'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def fingerprint(session, org_id):
    rows = session.scalars(select(QualityFeedback).where(QualityFeedback.org_id == org_id)
                           .order_by(QualityFeedback.id)).all()
    return digest([dict(out(r), history=review_history(session, r)) for r in rows])


def main():
    csv.field_size_limit(16 * 1024 * 1024)
    if (DEST / 'manifest.json').exists():
        raise SystemExit('Frozen v1 already exists; refusing to overwrite.')
    url = make_url(get_settings().database_url)
    assert url.database == 'ltc_clean'
    engine = create_engine(url)
    with Session(engine) as db:
        db.execute(text('SET TRANSACTION READ ONLY'))
        org = db.scalar(select(Organization).where(Organization.code == 'JIAAN'))
        admin = db.scalar(select(User).where(User.org_id == org.id, User.role == 'admin')
                          .order_by(User.username))
        assert admin is not None and admin.role == 'admin'
        stats = gold_stats(user=admin, db=db)
        assert stats == dict(pending_review=0, needs_review=0, ready=18, not_eligible=0), stats
        before = fingerprint(db, org.id)
        kb = [dict(document_id=str(d.id), title=d.title, version_id=str(v.id),
                   version_label=v.version_label, status=v.status, file_sha256=v.file_sha256,
                   chunk_count=v.chunk_count, effective_from=v.effective_from, effective_to=v.effective_to)
              for d, v in db.execute(select(Document, DocumentVersion)
                .join(DocumentVersion, DocumentVersion.document_id == Document.id)
                .where(or_(Document.org_id == org.id, Document.org_id.is_(None)), DocumentVersion.status == 'published')
                .order_by(Document.id, DocumentVersion.id))]
        org_id, admin_id, facility_type = org.id, admin.id, org.facility_type
        db.rollback()
    DEST.mkdir(parents=True, exist_ok=True)
    with Session(engine) as db:
        admin = db.get(User, admin_id)
        bodies = {}
        for fmt in ('json', 'jsonl', 'csv'):
            # Actual API handler, same admin role guard, org filter, encoder and
            # audit as GET /api/quality/dataset/gold/export?format=...
            response = export_gold(format=fmt, user=admin, db=db)
            assert response.status_code == 200
            bodies[fmt] = response.body
        records = json.loads(bodies['json'])['records']
        assert len(records) == 18
        assert all(r['status'] == 'verified' and r['gold_readiness'] == 'ready' for r in records)
        assert len([x for x in bodies['jsonl'].decode().splitlines() if x.strip()]) == 18
        assert len(list(csv.DictReader(io.StringIO(bodies['csv'].decode('utf-8-sig'))))) == 18
        assert [r['id'] for r in records] == [json.loads(line)['id'] for line in bodies['jsonl'].decode().splitlines()]
        for fmt, body in bodies.items():
            (DEST / f'gold_dataset_v1.{fmt}').write_bytes(body)
        after = fingerprint(db, org_id)
        assert after == before, 'Gold data changed during export'
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        commit = None
    manifest = dict(dataset_version='gold_v1_20261011', exported_at=datetime.now(timezone.utc).isoformat(),
                    total_cases=18, source='verified + ready feedback', runtime_database='ltc_clean',
                    org_id=str(org_id), institution='JIAAN', facility_type=facility_type,
                    intended_use='development Gold regression set', dataset_split=None,
                    qa_policy_version=DEFAULT_POLICY.version,
                    safety_policy_version=DEFAULT_POLICY.safety_version,
                    clarification_policy_version=DEFAULT_POLICY.clarification_version,
                    kb_version='sha256:' + digest(kb), kb_versions=kb, git_commit=commit,
                    git_commit_note=None if commit else 'Not available: project is not a Git checkout',
                    code_versions=versions(), feedback_review_fingerprint=before,
                    gold_data_unchanged=before == after,
                    export_api='/api/quality/dataset/gold/export',
                    export_transport='existing API handler invoked in-process with same-org DB admin; no production code changes',
                    export_audit='Three normal export audit entries created by existing API',
                    sha256={fmt: hashlib.sha256(body).hexdigest() for fmt, body in bodies.items()})
    (DEST / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(json.dumps(dict(status=stats, total_cases=18, gold_data_unchanged=True, destination=str(DEST)), ensure_ascii=False))
    engine.dispose()


if __name__ == '__main__':
    main()

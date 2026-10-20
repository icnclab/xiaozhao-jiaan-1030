"""Read-only retrieval ranking report using configured DB and embedding provider."""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select, text
from app.db import new_session
from app.models import Organization
from app.providers.embedding import get_embedding_provider
from app.services.retrieval import retrieve

parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
parser.add_argument('--question', default='我可以幫他換藥嗎？')
parser.add_argument('--org-code')
args = parser.parse_args()
with new_session() as session:
    session.execute(text('SET TRANSACTION READ ONLY'))
    orgs = session.scalars(select(Organization).order_by(Organization.code)).all()
    print('Organizations:', [(o.code, o.facility_type) for o in orgs])
    org = next((o for o in orgs if o.code == args.org_code), None) if args.org_code else next((o for o in orgs if o.facility_type == 'home'), orgs[0])
    if org is None:
        raise SystemExit('Unknown organization')
    results = retrieve(session, args.question, org.id, org.facility_type, date(2026, 10, 8))
    data = {'question': args.question, 'org_code': org.code, 'facility_type': org.facility_type,
            'date': '2026-10-08', 'embedding_model': get_embedding_provider().model,
            'results': [{'rank': i, 'combined': r.combined, 'coverage': r.coverage,
                         'vector': r.vector, 'document': r.title, 'locator': r.locator,
                         'hybrid_score': r.hybrid_score, 'topic_relevance': r.topic_relevance,
                         'title_bonus': r.title_bonus, 'intent_bonus': r.intent_bonus,
                         'chunk_id': str(r.chunk_id), 'text': r.text}
                        for i, r in enumerate(results, 1)]}
    Path(args.output).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    for r in data['results'][:15]:
        print('{rank:2} | {combined:.4f} | {coverage:.4f} | {vector:.4f} | {document} | {locator}'.format(**r))
    print('TARGET CHUNKS:')
    for r in data['results']:
        if '1090119919' in r['document']:
            print(json.dumps(r, ensure_ascii=False))

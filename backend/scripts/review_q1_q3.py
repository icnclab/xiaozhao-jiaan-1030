"""Compare the regression output with historical citation documents (read-only)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from app.db import new_session

root = Path(__file__).resolve().parents[2]
results = json.loads((root / 'docs/q1_q3_after.json').read_text(encoding='utf-8'))
session = new_session()
session.execute(text('SET TRANSACTION READ ONLY'))
summary = []
for row in results:
    cited = {row['evidence'][ref]['title'] for claim in row['claims'] for ref in claim['refs']}
    answer = ' '.join(c['text'] for c in row['claims'])
    if row['id'].startswith('formal_'):
        expected_docs = set(session.execute(text('''
            SELECT DISTINCT d.title FROM citations ci
            JOIN document_versions dv ON dv.id=ci.version_id
            JOIN documents d ON d.id=dv.document_id
            WHERE ci.qa_item_id=(SELECT id FROM qa_items WHERE question_masked=:q ORDER BY created_at DESC LIMIT 1)
        '''), {'q': row['question']}).scalars())
        passed = row['outcome_match'] and (not expected_docs or cited == expected_docs)
    elif row['id'].startswith('Q1'):
        passed = row['outcome'] == 'answer' and cited == {'長期照顧服務人員訓練認證繼續教育及登錄辦法'}
        passed = passed and '六個月內' in answer and '有效期限屆至前' in answer
        passed = passed and any(row['evidence'][ref]['locator'] == '第 12 條' for c in row['claims'] for ref in c['refs'])
    else:
        passed = row['outcome'] == 'answer' and cited == {'附件一-115年度居家式長期照顧服務機構評鑑基準'}
        passed = passed and ('3 個月' in answer or '3個月' in answer or '三個月' in answer)
        passed = passed and '行政聯繫會議' in answer
    summary.append(dict(id=row['id'], passed=passed, cited=sorted(cited), answer=answer, timings=row['timings']))
    print(row['id'], passed, answer, sorted(cited), flush=True)
(root / 'docs/q1_q3_review.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
session.rollback()
session.close()
print('Passed:', sum(r['passed'] for r in summary), '/', len(summary))
sys.exit(0 if all(r['passed'] for r in summary) else 1)

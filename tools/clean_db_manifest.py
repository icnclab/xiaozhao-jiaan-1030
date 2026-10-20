"""Read-only formal-source preflight; never imports seed scripts or writes a DB."""
import ast
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.ingest import parse, chunk

SOURCE = Path('C:/Phase1知識庫/小照_正式資料')

def targets(filename):
    tree = ast.parse((ROOT / 'tools' / filename).read_text(encoding='utf-8-sig'))
    return next(ast.literal_eval(n.value) for n in tree.body
                if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'TARGETS' for t in n.targets))

def main():
    meta = {}
    for title, values in targets('publish_formal_law.py').items():
        meta[title] = dict(effective_from=values[1], source=values[2], doc_type='regulation')
    for title, values in targets('publish_phase1_kb_14.py').items():
        meta[title] = dict(effective_from=values[0], source=values[1], doc_type='other')
    for title, values in targets('publish_phase1_kb.py').items():
        meta[title] = dict(effective_from=values['effective_from'], source=values['source'], doc_type='other')
    approved, excluded = [], []
    for path in sorted(SOURCE.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(SOURCE)
        if path.stem not in meta or rel.parts[0] not in {'01_法規資料庫', '02_知識庫'}:
            excluded.append({'path': str(rel), 'reason': 'outside existing formal publish allowlist (archive, backup, test or administrative file)'})
            continue
        data = path.read_bytes()
        parsed = parse(data)
        drafts, warnings = chunk(parsed)
        approved.append(dict(path=str(rel), sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
                             title=path.stem, **meta[path.stem], chunks=len(drafts),
                             warnings=parsed.warnings + warnings))
    missing = sorted(set(meta) - {d['title'] for d in approved})
    result = dict(source_root=str(SOURCE), hostname=__import__('socket').gethostname(),
                  approved=approved, excluded=excluded, missing=missing)
    (ROOT / 'docs' / 'clean-db-manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'approved': len(approved), 'excluded': len(excluded), 'missing': missing,
                      'chunks': sum(d['chunks'] for d in approved),
                      'warnings': [(d['title'], d['chunks'], d['warnings']) for d in approved if d['warnings'] or not d['chunks']]}, ensure_ascii=False))

if __name__ == '__main__':
    main()

"""Guarded clean-DB provisioning. Old ltc is only ever queried READ ONLY.

Run with backend/.venv/Scripts/python.exe tools/clean_db.py ACTION [DB].
No destructive/reseed/reset operations are provided.
"""
import ast
import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

PRIVATE = ROOT / 'run' / 'clean-db-private'
DOCS = ROOT / 'docs'
ALLOWED = {'ltc_clean', 'ltc_clean_verify'}
ENV = dotenv_values(ROOT / '.env')
OLD_URL = make_url(ENV['DATABASE_URL'])
assert OLD_URL.host == '127.0.0.1' and OLD_URL.port == 55432

def private_init():
    PRIVATE.mkdir(parents=True, exist_ok=True)
    # Restrict secret files to this Windows account, SYSTEM and Administrators.
    who = subprocess.check_output(['whoami', '/user', '/fo', 'csv', '/nh'], text=True).strip()
    import csv
    sid = next(csv.reader([who]))[1]
    result = subprocess.run(['icacls', str(PRIVATE), '/inheritance:r', '/grant:r',
                             f'*{sid}:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F'],
                            capture_output=True)
    if result.returncode:
        raise RuntimeError('Private directory ACL failed')

def save(name, obj):
    (DOCS / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

def url_for(db):
    assert db in ALLOWED, 'Writes allowed only in new databases'
    return OLD_URL.set(database=db)

def snapshot_old():
    engine = create_engine(OLD_URL)
    with engine.connect() as c, c.begin():
        c.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        assert c.scalar(text('SELECT current_database()')) == 'ltc'
        tables = c.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")).all()
        rows = {}
        for table in tables:
            assert table.replace('_', '').isalnum()
            count = c.scalar(text(f'SELECT count(*) FROM "{table}"'))
            # No row values or personal information leave the server.
            fingerprint = c.scalar(text(f'''SELECT md5(coalesce(string_agg(h, '' ORDER BY h), ''))
                FROM (SELECT md5(row_to_json(t)::text) h FROM "{table}" t) s'''))
            rows[table] = dict(count=count, fingerprint=fingerprint)
        return dict(database='ltc', host=OLD_URL.host, port=OLD_URL.port,
                    captured_at=datetime.now().isoformat(), tables=rows,
                    schema=c.scalar(text('SELECT version_num FROM alembic_version')))

def baseline():
    assert OLD_URL.database == 'ltc', 'Baseline must precede cutover'
    private_init()
    backup = PRIVATE / 'original.env'
    if backup.exists():
        raise RuntimeError('Baseline already exists; refusing overwrite')
    shutil.copyfile(ROOT / '.env', backup)
    state = dict(old_db='ltc', old_data_dir=ENV.get('DATA_DIR'), clean_db='ltc_clean',
                 clean_data_dir=str(ROOT / 'data_clean'), created_at=datetime.now().isoformat())
    (PRIVATE / 'profile.json').write_text(json.dumps(state), encoding='utf-8')
    credentials = {name: secrets.token_urlsafe(20) for name in ['jiaan_admin', 'jiaan_sv01', 'jiaan_sv02']}
    (PRIVATE / 'credentials.json').write_text(json.dumps(credentials, indent=2), encoding='utf-8')
    save('clean-db-old-before.json', snapshot_old())
    protected = [p for folder in ['backend/app', 'frontend/src'] for p in (ROOT / folder).rglob('*')
                 if p.suffix in {'.py', '.ts', '.tsx', '.vue', '.js'}]
    save('clean-db-code-before.json', {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected})
    print('Baseline saved; .env backup and new passwords stored privately (not printed).')

def create(db):
    url = url_for(db)
    admin_engine = create_engine(OLD_URL.set(database='postgres'), isolation_level='AUTOCOMMIT')
    with admin_engine.connect() as c:
        if c.scalar(text('SELECT 1 FROM pg_database WHERE datname=:d'), {'d': db}):
            raise RuntimeError('Database exists; refusing reuse or overwrite')
        c.execute(text(f'CREATE DATABASE "{db}" TEMPLATE template0'))
    os.environ['DATABASE_URL'] = url.render_as_string(hide_password=False)
    os.environ['ALEMBIC_DATABASE_URL'] = os.environ['DATABASE_URL']
    from alembic import command
    from alembic.config import Config
    cfg = Config(str(ROOT / 'backend' / 'alembic.ini'))
    cfg.set_main_option('script_location', str(ROOT / 'backend' / 'migrations'))
    command.upgrade(cfg, 'head')
    engine = create_engine(url)
    with engine.connect() as c:
        assert c.scalar(text('SELECT current_database()')) == db
        assert c.scalar(text('SELECT count(*) FROM users')) == 0
    print(f'{db}: created from template0; existing Alembic upgrade head completed.')

def configure(db):
    url = url_for(db)
    os.environ['DATABASE_URL'] = url.render_as_string(hide_password=False)
    os.environ['DATA_DIR'] = str(ROOT / ('data_clean' if db == 'ltc_clean' else 'data_clean_verify'))
    if db == 'ltc_clean_verify':
        os.environ['LINE_MODE'] = 'mock'
        os.environ['APP_ENV'] = 'test'
    from app.db import new_session
    with new_session() as s:
        assert s.scalar(text('SELECT current_database()')) == db

def ingest(db):
    configure(db)
    from sqlalchemy import select
    from app.auth import set_password
    from app.db import session_scope
    from app.models import Organization, User, Category, DocumentVersion
    from app.services import documents
    from app.worker import run_one
    manifest = json.loads((DOCS / 'clean-db-manifest.json').read_text(encoding='utf-8'))
    assert socket.gethostname().upper() == 'STUST'
    assert len(manifest['approved']) == 32 and not manifest['missing']
    credentials = json.loads((PRIVATE / 'credentials.json').read_text(encoding='utf-8'))
    with session_scope() as s:
        assert s.scalar(text('SELECT count(*) FROM users')) == 0, 'No reseeding allowed'
        org = Organization(code='JIAAN', name='嘉安居家服務', facility_type='home')
        s.add(org)
        s.flush()
        users = {}
        for role, names in [('admin', ['jiaan_admin']), ('supervisor', ['jiaan_sv01','jiaan_sv02']),
                            ('caregiver', [f'jiaan_cg{i:02}' for i in range(1,5)])]:
            for name in names:
                u = User(org_id=org.id, username=name, display_name=name, role=role, is_active=True)
                if role != 'caregiver':
                    set_password(u, credentials[name])
                s.add(u)
                s.flush()
                users[name] = u
        # Only the generic routing names; no demo templates, documents, accounts or bindings.
        tree = ast.parse((ROOT / 'backend/scripts/seed_demo.py').read_text(encoding='utf-8'))
        cats = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'CATEGORIES' for t in n.targets))
        for order, (name, _) in enumerate(cats):
            s.add(Category(org_id=org.id, name=name, sort_order=order,
                           default_assignee_id=users['jiaan_sv01' if order % 2 == 0 else 'jiaan_sv02'].id))
        for item in manifest['approved']:
            path = Path(manifest['source_root']) / item['path']
            data = path.read_bytes()
            assert hashlib.sha256(data).hexdigest() == item['sha256'], 'Source changed after approval'
            document = documents.create_document(s, users['jiaan_admin'], title=item['title'],
                            doc_type=item['doc_type'], scope='shared', facility_types=['home'])
            documents.add_version(s, users['jiaan_admin'], document, file_name=path.name, data=data,
                            version_label='STUST_clean_20261010_v1', effective_from=date.fromisoformat(item['effective_from']),
                            effective_to=None, source=item['source'], source_url=None)
    worker_id = f'{socket.gethostname()}-{os.getpid()}'
    processed = 0
    while run_one(worker_id, ['doc_ingest']):
        processed += 1
        print(f'{db}: ingest {processed}/32', flush=True)
    publish(db)

def publish(db):
    configure(db)
    from sqlalchemy import select
    from app.db import session_scope
    from app.models import User, DocumentVersion
    from app.services import documents
    with session_scope() as s:
        admin = s.scalar(select(User).where(User.username == 'jiaan_admin'))
        versions = s.scalars(select(DocumentVersion)).all()
        assert len(versions) == 32
        for v in versions:
            allowed_warning = '法規類文件未偵測到「第 X 條」結構，已改按段落切塊'
            assert v.status == 'review' and v.chunk_count > 0 and all(w == allowed_warning for w in v.warnings), 'Parse issue; do not publish'
            documents.publish(s, admin, v)
    check(db)

def check(db):
    configure(db)
    from app.db import new_session
    manifest = json.loads((DOCS / 'clean-db-manifest.json').read_text(encoding='utf-8'))
    with new_session() as s:
        s.execute(text('SET TRANSACTION READ ONLY'))
        tables = s.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")).all()
        counts = {t: s.scalar(text(f'SELECT count(*) FROM "{t}"')) for t in tables}
        roles = dict(s.execute(text('SELECT role,count(*) FROM users GROUP BY role')).all())
        versions = s.execute(text('SELECT d.title,v.file_sha256,v.file_path,v.chunk_count,v.status FROM document_versions v JOIN documents d ON d.id=v.document_id')).mappings().all()
        expected = {d['title']: d for d in manifest['approved']}
        assert len(versions) == len(expected)
        for v in versions:
            assert v['file_sha256'] == expected[v['title']]['sha256'] == hashlib.sha256(Path(v['file_path']).read_bytes()).hexdigest()
            assert v['status'] == 'published' and v['chunk_count'] == expected[v['title']]['chunks']
        vectors = s.scalar(text('SELECT count(*) FROM chunks WHERE embedding IS NOT NULL AND tsv IS NOT NULL'))
        workers = s.execute(text("SELECT locked_by,count(*) FROM jobs WHERE kind='doc_ingest' AND status='done' GROUP BY locked_by")).all()
        assert sum(n for _,n in workers) == 32 and all(w.startswith('STUST-') for w,n in workers)
        assert vectors == counts['chunks'] == sum(d['chunks'] for d in expected.values())
        if db == 'ltc_clean':
            for t in ['cases','qa_items','line_accounts','binding_codes','transcripts','transcript_segments',
                      'transcript_revisions','tts_assets','sessions','case_events','case_messages','citations','line_events','notification_jobs']:
                assert counts[t] == 0, f'Clean initial state violated: {t}'
            assert roles == {'caregiver':4,'supervisor':2,'admin':1}
            assert s.scalar(text("SELECT count(*) FROM jobs WHERE kind<>'doc_ingest' OR status<>'done'")) == 0
        out = dict(database=db, host='127.0.0.1', port=55432, counts=counts, roles=roles,
                   vectors=vectors, conversations=s.scalar(text('SELECT count(DISTINCT conversation_id) FROM qa_items')),
                   ingest_workers=[dict(worker=w,count=n) for w,n in workers], manifest_verified=True,
                   embedding_models=s.scalars(text('SELECT DISTINCT embedding_model FROM chunks')).all())
        save(f'clean-db-{db}-counts.json', out)
        print(json.dumps(out, ensure_ascii=False))

def compare():
    # After cutover use the protected original credentials, never the switched target.
    global OLD_URL
    OLD_URL = make_url(dotenv_values(PRIVATE / 'original.env')['DATABASE_URL'])
    after = snapshot_old()
    before = json.loads((DOCS / 'clean-db-old-before.json').read_text(encoding='utf-8'))
    changed = {t: dict(before=before['tables'][t]['count'], after=v['count'])
               for t,v in after['tables'].items() if v != before['tables'][t]}
    save('clean-db-old-after.json', after)
    save('clean-db-old-comparison.json', dict(changed_tables=changed,
         business_unchanged=not any(t != 'worker_heartbeats' for t in changed)))
    print(json.dumps({'changed_tables':changed}, ensure_ascii=False))
    if any(t != 'worker_heartbeats' for t in changed):
        raise RuntimeError('Old DB changed during preparation; stop before switching')

if __name__ == '__main__':
    action = sys.argv[1]
    if action == 'baseline': baseline()
    elif action == 'compare': compare()
    elif action == 'create': create(sys.argv[2])
    elif action == 'ingest': ingest(sys.argv[2])
    elif action == 'check': check(sys.argv[2])
    elif action == 'publish': publish(sys.argv[2])
    else: raise SystemExit('Unknown action')

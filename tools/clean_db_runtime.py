"""Read-only live API database identity and PostgreSQL activity; no secrets."""
import json
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import clean_db as provision
import httpx
from sqlalchemy import create_engine, text

phase = sys.argv[1]
expected = 'ltc' if phase == 'before' else 'ltc_clean'
url = provision.OLD_URL
assert url.database == expected
# /api/healthz is now minimal for anonymous/public (Tailscale Funnel) callers;
# this local-only token (same file deploy/fieldtest/*.ps1 use) gets the full
# payload including database_name back, without needing any new login flow.
_token_file = Path(__file__).resolve().parents[1] / 'deploy' / 'fieldtest' / 'run' / 'internal_health_token.txt'
_headers = {}
if _token_file.is_file():
    _token = _token_file.read_text(encoding='utf-8').strip()
    if _token:
        _headers['X-Internal-Health-Token'] = _token
health = httpx.get('http://127.0.0.1:8140/api/healthz', timeout=10, headers=_headers).json()
with create_engine(url).connect() as c, c.begin():
    c.execute(text('SET TRANSACTION READ ONLY'))
    actual = c.scalar(text('SELECT current_database()'))
    cluster = c.execute(text('SELECT system_identifier FROM pg_control_system()')).scalar()
    connections = [dict(r) for r in c.execute(text("""SELECT datname,application_name,client_addr::text,client_port,state,
        backend_start FROM pg_stat_activity WHERE backend_type='client backend' AND pid<>pg_backend_pid()
        ORDER BY datname,backend_start""")).mappings()]
    workers = [dict(r) for r in c.execute(text('SELECT worker_id,seen_at FROM worker_heartbeats ORDER BY seen_at DESC LIMIT 2')).mappings()]
assert actual == expected and health['db'] == 'ok'
if phase != 'before':
    assert health.get('database_name') == expected, 'Live API engine does not use expected DB'
    assert connections and all(r['datname'] == expected for r in connections), 'Unexpected remaining DB runtime sessions'
out = dict(phase=phase, captured_at=datetime.now().isoformat(), expected=expected,
           host=url.host,port=url.port,database=actual,live_api_health=health,
           pg_system_identifier=str(cluster),pg_connections=connections,worker_heartbeats=workers)
provision.save(f'clean-db-runtime-{phase}.json',out)
print(json.dumps(out, default=str, ensure_ascii=False))

"""One-command profile switch; changes only DATABASE_URL and DATA_DIR.

Does not start/stop services, run migrations, or write any PostgreSQL records.
"""
import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'run/clean-db-private'
parser = argparse.ArgumentParser()
parser.add_argument('--target', choices=['old', 'clean'], required=True)
parser.add_argument('--check', action='store_true')
args = parser.parse_args()
state = json.loads((PRIVATE / 'profile.json').read_text(encoding='utf-8'))
env = dotenv_values(ROOT / '.env')
url = make_url(env['DATABASE_URL'])
assert url.host == '127.0.0.1' and url.port == 55432 and url.database in {'ltc','ltc_clean'}
assert not os.environ.get('DATABASE_URL'), 'Process environment overrides .env; remove override before switching'
database = 'ltc' if args.target == 'old' else 'ltc_clean'
directory = state['old_data_dir'] if args.target == 'old' else state['clean_data_dir']
assert directory and Path(directory).exists(), 'Target DATA_DIR does not exist'
target = url.set(database=database)
with create_engine(target).connect() as c, c.begin():
    c.execute(text('SET TRANSACTION READ ONLY'))
    assert c.scalar(text('SELECT current_database()')) == database
    assert c.scalar(text('SELECT version_num FROM alembic_version')) == '0001'
    info = {t:c.scalar(text(f'SELECT count(*) FROM {t}')) for t in ['users','cases','qa_items','line_accounts','documents','chunks']}
    assert info['users'] >= 7 and info['documents'] >= 32 and info['chunks'] > 0
print(json.dumps(dict(target=database, host=target.host, port=target.port, data_dir=directory, counts=info)))
if args.check:
    sys.exit(0)
original = (ROOT / '.env').read_bytes()
backup = PRIVATE / ('before_' + args.target + '_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.env')
backup.write_bytes(original)
content = original.decode('utf-8-sig')
newline = '\r\n' if '\r\n' in content else '\n'
updates = {'DATABASE_URL':target.render_as_string(hide_password=False), 'DATA_DIR':Path(directory).as_posix()}
for key, value in updates.items():
    pattern = r'(?m)^' + key + r'=.*$'
    if re.search(pattern, content):
        content = re.sub(pattern, lambda _: key + '=' + value + ('\r' if newline == '\r\n' else ''), content)
    else:
        content = content.rstrip('\r\n') + newline + key + '=' + value + newline
temporary = ROOT / '.env.clean_switch_tmp'
temporary.write_bytes(content.encode('utf-8'))
updated = dotenv_values(temporary)
assert all(updated.get(k) == v for k,v in env.items() if k not in updates), 'Unrelated setting changed'
os.replace(temporary, ROOT / '.env')
print(f'Profile changed to {database}; only DATABASE_URL and DATA_DIR changed. Restart aa API/worker.')

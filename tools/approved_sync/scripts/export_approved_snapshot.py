#!/usr/bin/env python3
"""Export audited source-only paths from an immutable git commit to a reproducible ZIP.

Fails closed on sensitive path names/content. Never reads working-tree data or .env.
Does not guarantee absence of personal data; the first use must undergo manual review.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

SOURCE_PREFIXES = (
    'backend/app/', 'backend/alembic/', 'backend/migrations/', 'backend/tests/',
    'backend/scripts/', 'backend/checks/', 'frontend/src/', 'frontend/public/',
    'deploy/fieldtest/', '.claude/skills/', '.githooks/', '.github/workflows/',
    'docs/uat/', 'docs/architecture/', 'docs/handover/', 'docs/sync/',
    'deploy/uat/', 'tools/approved_sync/',
)
SOURCE_FILES = {
    'README.md', 'CLAUDE.md', '.gitignore', 'requirements-test.txt',
    '.claude/github-sync.json', 'backend/uv.lock',
    'backend/requirements.txt', 'backend/requirements-test.txt',
    'backend/pyproject.toml', 'backend/alembic.ini',
    'frontend/package.json', 'frontend/package-lock.json',
    'frontend/vite.config.ts', 'frontend/vite.config.js',
    'frontend/index.html', 'frontend/tsconfig.json',
    'frontend/tsconfig.app.json', 'frontend/tsconfig.node.json',
    'docker-compose.yml', 'docker-compose.yaml', 'Dockerfile',
}
TEXT_EXTENSIONS = {
    '.py', '.ts', '.tsx', '.js', '.jsx', '.json', '.md', '.txt', '.css', '.html',
    '.yml', '.yaml', '.toml', '.ini', '.cfg', '.sh', '.ps1', '.lock', '.sql',
}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.svg', '.webp', '.ico'}
DENY_PARTS = {
    '.git', '.venv', 'node_modules', '__pycache__', 'backups', 'backup', 'tmp',
    'temp', 'uploads', 'data', 'data_clean', 'data_demo', 'recordings', 'interviews', 'logs', 'run',
    '.local_webpush_secrets', 'secrets', 'private_data', 'dist', 'build',
}
DENY_NAMES = (
    '.env', '.env.', '.local.env', '.backup', '.pem', '.key', '.p12', '.pfx',
    'credentials.json', 'secrets.json', 'restore_log', 'production_patch',
    'real_interviews', 'participant_mapping', 'transcript_raw', '.local.json',
)
# Fail on likely active credentials. This intentionally does not attempt full DLP.
SECRET_RULES = {
    'private_key': re.compile(r'-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----'),
    'github_token': re.compile(r'\b(?:ghp_|gho_|ghs_|ghu_|ghr_)[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{50,}\b'),
    'aws_access_key': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'slack_token': re.compile(r'\bxox[baprs]-[A-Za-z0-9-]{20,}\b'),
    'db_dsn_password': re.compile(r'postgres(?:ql)?(?:\+\w+)?://[^\s:@]+:[^\s@/]+@', re.I),
    'line_token_assignment': re.compile(r'(?i)\b(?:LINE_CHANNEL_ACCESS_TOKEN|LINE_CHANNEL_SECRET|DATA_ENCRYPTION_KEY)\s*[:=]\s*["\']?[A-Za-z0-9+/=_-]{24,}'),
    'taiwan_id': re.compile(r'(?<![A-Za-z0-9])[A-Z][12][0-9]{8}(?![A-Za-z0-9])'),
    'mobile_number': re.compile(r'(?<![0-9])09[0-9]{8}(?![0-9])'),
}
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 45 * 1024 * 1024


def git_bytes(repo: Path, *args: str) -> bytes:
    cmd = ['git', '-C', str(repo), *args]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode:
        err = proc.stderr.decode('utf-8', errors='replace').strip()
        raise RuntimeError('Git export command failed; credential-bearing CLI output withheld')
    return proc.stdout


def eligible(path: str) -> bool:
    p = PurePosixPath(path)
    if p.is_absolute() or '..' in p.parts or '\\' in path:
        return False
    lower = path.lower()
    parts = {s.lower() for s in p.parts}
    if parts & DENY_PARTS:
        return False
    basename = p.name.lower()
    template=lower in {'.env.example','deploy/uat/uat.env.example'}
    if any(x in basename for x in DENY_NAMES) and not template:
        return False
    if template or lower in {'deploy/uat/least_privilege.sql.example','deploy/uat/pg_hba.conf.example','deploy/uat/caddyfile.example'}:
        return True
    if lower not in {x.lower() for x in SOURCE_FILES} and not any(lower.startswith(x.lower()) for x in SOURCE_PREFIXES):
        return False
    ext = p.suffix.lower()
    if ext in TEXT_EXTENSIONS:
        # SQL is permitted only when part of the versioned migration tree.
        if ext == '.sql' and not lower.startswith(('backend/alembic/', 'backend/migrations/')):
            return False
        # Test fixtures and docs may contain interview excerpts; require separate human approval.
        if lower.startswith('docs/uat/') and ext not in {'.md', '.txt'}:
            return False
        return True
    return ext in IMAGE_EXTENSIONS and lower.startswith(('frontend/src/', 'frontend/public/'))


def reviewed_synthetic_match(path, blob, rule, matched):
    ledger=Path(__file__).resolve().parents[1]/'config/reviewed_synthetic_matches.json'
    if not ledger.is_file():return False
    entry=json.loads(ledger.read_text(encoding='utf-8')).get('files',{}).get(path,{})
    return entry.get('fileSha256')==hashlib.sha256(blob.replace(b'\r\n',b'\n')).hexdigest() and hashlib.sha256(matched.encode()).hexdigest() in entry.get('matchedSha256',{}).get(rule,[])


def scan_content(path: str, blob: bytes) -> None:
    if len(blob) > MAX_FILE_BYTES:
        raise ValueError(f'File exceeds export size limit: {path}')
    if PurePosixPath(path).suffix.lower() in IMAGE_EXTENSIONS:
        return
    try:
        decoded = blob.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError(f'Non-UTF8 source needs manual review: {path}') from exc
    for name, rule in SECRET_RULES.items():
        hits=list(rule.finditer(decoded))
        if name=='db_dsn_password':
            hits=[m for m in hits if not re.search(r':REPLACE_[A-Z0-9_]+@$',m.group())]
        if name=='line_token_assignment':
            hits=[m for m in hits if not re.search(r'[=:]\s*[\"\']?REPLACE_[A-Z0-9_]+$',m.group())]
        if name=='db_dsn_password':
            hits=[m for m in hits if not re.search(r':\$\{[A-Z0-9_]+(?::\?[^}]+)?\}@$',m.group())]
        hits=[m for m in hits if not reviewed_synthetic_match(path,blob,name,m.group())]
        if hits:
            raise ValueError(f'Possible {name} in {path}; review locally (content not printed)')


def export(repo: Path, commit: str, output: Path) -> dict:
    if not re.fullmatch('[0-9a-fA-F]{40}', commit):
        raise ValueError('Commit must be a complete 40-char git SHA')
    objtype = git_bytes(repo, 'cat-file', '-t', commit).decode().strip()
    if objtype != 'commit':
        raise ValueError('Requested SHA is not a commit')
    raw_names = git_bytes(repo, 'ls-tree', '-r', '--name-only', '-z', commit)
    all_paths = sorted(set(x.decode('utf-8') for x in raw_names.split(b'\0') if x))
    chosen = [p for p in all_paths if eligible(p)]
    if not chosen:
        raise ValueError('No approved source files in selected commit')
    manifest_files = []
    blobs = []
    total = 0
    for path in chosen:
        blob = git_bytes(repo, 'show', f'{commit}:{path}')
        scan_content(path, blob)
        total += len(blob)
        if total > MAX_TOTAL_BYTES:
            raise ValueError('Archive is unexpectedly large; manual approval required')
        manifest_files.append({'path': path, 'sha256': hashlib.sha256(blob).hexdigest(), 'bytes': len(blob)})
        blobs.append((path, blob))
    manifest = {
        'schema': 'xiaozhao-code-snapshot-v1',
        'source_commit': commit.lower(),
        'included_files': len(chosen),
        'excluded_from_export': len(all_paths) - len(chosen),
        'selection_policy': 'source-only allowlist; privacy screening required before initial rollout',
        'cloud_upload_status': 'not_yet_verified',
        'files': manifest_files,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    # Deterministic ZIP per commit; no clock-based manifest values.
    with zipfile.ZipFile(output, mode='w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, blob in blobs + [('_snapshot_manifest.json', (json.dumps(manifest, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))]:
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, blob, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return {
        'commit': commit.lower(),
        'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
        'files': len(chosen),
        'bytes': output.stat().st_size,
        'path': str(output),
        'cloud_verified': False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', required=True)
    p.add_argument('--commit', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    try:
        print(json.dumps(export(Path(args.repo), args.commit, Path(args.output)), ensure_ascii=False))
    except Exception as exc:
        print(f'EXPORT_BLOCKED: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

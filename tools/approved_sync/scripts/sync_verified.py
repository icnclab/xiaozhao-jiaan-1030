#!/usr/bin/env python3
"""Synchronize an already-reviewd stable GitHub commit to the lab's Google Drive.

Only the established GitHub checker may push pre-tagged commits; this program
never stages or commits changes, switches branches, or touches databases.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from export_approved_snapshot import export, git_bytes, eligible
from google_drive_api import GoogleDriveBackup


def run(cmd, *, cwd=None, check=True, timeout=300):
    p = subprocess.run([str(x) for x in cmd], cwd=cwd, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, text=True, encoding='utf-8',
                       errors='replace', timeout=timeout, check=False)
    if check and p.returncode:
        # Do not print command stderr: third-party CLI may accidentally echo credentials.
        raise RuntimeError(f'Command unsuccessful: {cmd[0]} (exit {p.returncode})')
    return p


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def md5(p: Path) -> str:
    h = hashlib.md5(usedforsecurity=False)
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def source_digest(repo, commit):
    paths=git_bytes(Path(repo),'ls-tree','-r','--name-only','-z',commit).decode('utf-8').split('\0')
    rows=[(p,hashlib.sha256(git_bytes(Path(repo),'show',f'{commit}:{p}')).hexdigest()) for p in sorted(paths) if p and eligible(p)]
    return hashlib.sha256(json.dumps(rows,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def verify_quality_gate(repo, commit):
    tags=run(['git','-C',repo,'ls-remote','--tags','origin','refs/tags/stable-ready-*'],timeout=60).stdout.splitlines()
    if not any(len(row.split())==2 and row.split()[0]==commit for row in tags):
        raise PermissionError('STABLE_READY_REMOTE_TAG_REQUIRED')
    raw=git_bytes(Path(repo),'show',f'{commit}:.claude/approved-sync-validation.json')
    receipt=json.loads(raw)
    required=('backend','typescript','frontend','sensitiveReview')
    if any(receipt.get(k)!='PASS' for k in required) or receipt.get('sourceDigest')!=source_digest(repo,commit):
        raise PermissionError('TESTED_SOURCE_RECEIPT_MISSING_OR_STALE')
    return receipt


def sync(cfg: dict, *, check_only=False) -> dict:
    repo = Path(cfg['repoPath']).resolve()
    if not (repo / '.git').exists():
        raise ValueError('RepoPath must be an existing Git working tree with .git')
    actual = run(['git', '-C', repo, 'remote', 'get-url', 'origin']).stdout.strip().rstrip('/')
    expected = cfg['expectedGitHubRemote'].strip().rstrip('/')
    if actual != expected:
        raise ValueError('GitHub origin differs from configured lab repository; no operation performed')
    branch = cfg['stableBranch']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/_-]{1,150}', branch) or '..' in branch:
        raise ValueError('Invalid stableBranch')
    info = {'repo': str(repo), 'stableBranch': branch, 'github': 'read-only',
            'drive': 'not_started', 'cloudVerified': False}
    if not check_only and cfg.get('driveEnabled', True) is not True:
        raise PermissionError('DRIVE_DISABLED_BY_USER')
    if cfg.get('allowGitHubAutoPush') and not check_only:
        expected_user = cfg.get('expectedGitHubAccount', '')
        if not expected_user:
            raise ValueError('expectedGitHubAccount missing')
        gh = shutil.which('gh')
        if not gh:
            raise RuntimeError('gh CLI not installed; GitHub push blocked')
        user = run([gh, 'api', 'user', '--jq', '.login'], timeout=25).stdout.strip()
        if user.lower() != expected_user.lower():
            raise PermissionError('GitHub logged-in account is not the configured laboratory account')
        script = repo / cfg.get('existingGithubSyncScript', '')
        if not script.is_file() or script.suffix.lower() != '.ps1':
            raise ValueError('Existing audited Github sync script not found')
        powershell = shutil.which('pwsh.exe') or shutil.which('pwsh')
        if not powershell:
            raise RuntimeError('PowerShell is required for existing Github sync script')
        p = run([powershell, '-NoProfile', '-NonInteractive', '-File', script, '-RepoRoot', repo], check=False, timeout=720)
        info['github'] = 'existing_checker_exit_' + str(p.returncode)
        # A skip/returncode=0 never means upload was successful. Remote SHA is authoritative.
    elif cfg.get('allowGitHubAutoPush') and check_only:
        info['github'] = 'check_only_no_push'

    # GitHub source is always an actual verified remote head, never the uncommitted working tree.
    remote_ref = f'refs/heads/{branch}'
    ls = run(['git', '-C', repo, 'ls-remote', '--heads', 'origin', branch], timeout=60).stdout.strip().splitlines()
    matches = [x.split()[0] for x in ls if len(x.split()) == 2 and x.split()[1] == remote_ref]
    if len(matches) != 1 or not re.fullmatch(r'[a-f0-9]{40}', matches[0]):
        raise ValueError('Verified stable branch does not exist in GitHub')
    commit = matches[0]
    run(['git', '-C', repo, 'fetch', '--no-tags', 'origin', f'{remote_ref}:refs/remotes/origin/{branch}'], timeout=120)
    local_sha = run(['git', '-C', repo, 'rev-parse', f'refs/remotes/origin/{branch}']).stdout.strip()
    if local_sha != commit:
        raise ValueError('Fetched GitHub SHA mismatch')
    info['githubRemoteCommit'] = commit
    info['github'] = 'remote_commit_verified' if info['github'] == 'read-only' else info['github'] + ';remote_commit_verified'
    if check_only:
        info['qualityGate'] = 'not_evaluated_check_only'
        info['drive'] = 'check_only_no_copy'
        return info
    verify_quality_gate(repo,commit)
    info['qualityGate']='remote_stable_tag_and_exact_tested_source_receipt'
    if not cfg.get('driveAccountCheckedByHuman', False):
        raise PermissionError('First manually confirm the lab Google Drive account and destination folder')

    staging = Path(os.environ.get('LOCALAPPDATA', tempfile.gettempdir())) / 'XiaoZhaoSync' / 'approved_snapshots'
    staging.mkdir(parents=True, exist_ok=True)
    output = staging / f'xiaozhao_code_{commit[:12]}.zip'
    archive = export(repo, commit, output)
    info['zipSha256'] = archive['sha256']
    info['sourceFiles'] = archive['files']
    filename = output.name
    lm_note = staging / f'待交給LM學習_{commit[:12]}.md'
    lm_note.write_text(
        '# 小照／嘉安：待交給 LM 學習的版本摘要\n\n'
        f'- 已經過私人 GitHub 穩定分支確認的 Commit：`{commit}`\n'
        f'- 本次可安全備份的程式／文件：{archive["files"]} 個檔案\n'
        f'- 來源分支：`{branch}`\n'
        '- 進度：僅完成穩定程式碼快照；**不代表新模組已正式部署或場測通過**。\n'
        '- 請先查看版本差異、架構變更及測試結果，再依既有 LM 規則提供給 LM 學習。\n'
        '- 請勿提供 `.env`、LINE 金鑰、資料庫 dump、訪談逐字稿、錄音或真實個資。\n'
        '- 註：這是自動提醒檔，**不是**自動將資料送給 LM。\n',
        encoding='utf-8')
    info['lmReminder'] = str(lm_note)
    if cfg.get('driveMode')!='api':raise ValueError('ONLY_OFFICIAL_GOOGLE_DRIVE_API_SUPPORTED')
    drive=GoogleDriveBackup(cfg)
    uploaded=drive.upload_verified(output,commit)
    note=drive.upload_verified(lm_note,commit)
    info.update(drive='google_drive_api_remote_md5_verified',cloudVerified=True,driveFileId=uploaded['fileId'],lmFileId=note['fileId'])
    return info


def append_event(logfile,event):
    with logfile.open('a',encoding='utf-8') as stream:
        stream.write(json.dumps(event,ensure_ascii=False)+'\n');stream.flush();os.fsync(stream.fileno())


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--config',required=True);ap.add_argument('--check-only',action='store_true');args=ap.parse_args()
    base=Path(os.environ.get('LOCALAPPDATA',tempfile.gettempdir()))/'XiaoZhaoSync';base.mkdir(parents=True,exist_ok=True)
    logs=base/'logs';logs.mkdir(exist_ok=True);logfile=logs/'dual_sync.jsonl';lock=base/'approved-sync.lock'
    event={'timeUTC':datetime.now(timezone.utc).isoformat(),'mode':'check' if args.check_only else 'sync'}
    held=False
    try:
        append_event(logfile,{**event,'result':'started'})
        with lock.open('x',encoding='utf-8') as f:f.write(str(os.getpid()))
        held=True
        cfg=json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
        out=sync(cfg,check_only=args.check_only)
        event.update(result='ok',commit=out.get('githubRemoteCommit',''),zipSha256=out.get('zipSha256',''),cloudVerified=out.get('cloudVerified',False),drive=out.get('drive',''))
        append_event(logfile,event)
        print(json.dumps(out,indent=2,ensure_ascii=False));return 0
    except Exception as exc:
        event.update(result='blocked',errorType=type(exc).__name__)
        try:append_event(logfile,event)
        except OSError:pass
        print('SYNC_BLOCKED: '+type(exc).__name__,file=sys.stderr);return 1
    finally:
        if held:lock.unlink()


if __name__ == '__main__':
    sys.exit(main())

"""Pinned, reviewed Git commits only. No auto-commit, DB, Drive or OAuth calls."""
import argparse,hashlib,json,os,re,subprocess,tempfile
from datetime import datetime,timezone
from pathlib import Path
from export_approved_snapshot import eligible,export,scan_content

REMOTE='https://github.com/icnclab/xiaozhao-jiaan-1030.git'
RECEIPT='.claude/approved-sync-validation.json'

class Skip(RuntimeError):pass

def git(repo,*args):
    p=subprocess.run(['git','-c','safe.directory='+Path(repo).resolve().as_posix(),'-C',str(repo),*args],capture_output=True,timeout=120)
    if p.returncode:raise RuntimeError('GIT_OPERATION_FAILED_OUTPUT_WITHHELD')
    return p.stdout

def remote_sha(repo,ref):
    rows=git(repo,'ls-remote','origin',ref).decode().splitlines()
    if not rows:return None
    if len(rows)!=1 or rows[0].split()[1]!=ref:raise RuntimeError('AMBIGUOUS_REMOTE_REF')
    return rows[0].split()[0]

def source_digest(repo,commit):
    paths=git(repo,'ls-tree','-r','--name-only','-z',commit).decode().split('\0')
    rows=[(p,hashlib.sha256(git(repo,'show',f'{commit}:{p}')).hexdigest()) for p in sorted(paths) if p and eligible(p)]
    return hashlib.sha256(json.dumps(rows,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def write_once(path,data):
    path=Path(path)
    if path.exists():
        if path.read_bytes()!=data:raise FileExistsError('EXISTING_ARTIFACT_DIFFERS')
        return
    with path.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())

def bundle(repo,commit,destination,receipt):
    out=Path(destination)/commit;out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out) as temporary:
        tmp=Path(temporary)/'source.zip';info=export(Path(repo),commit,tmp)
        name=f'xiaozhao_code_{commit[:12]}.zip';write_once(out/name,tmp.read_bytes())
    digest=info['sha256']
    version=(f'# 小照穩定版本\n\nCommit: `{commit}`\n\n'
             f'GitHub branch: `sync/approved-{commit[:12]}`\n\nSHA256: `{digest}`\n\n'
             f'白名單來源檔數：{info["files"]}；測試／審核 receipt：'+json.dumps(receipt,ensure_ascii=False)+'\n\n'
             '僅程式來源備份，不是資料庫備份或部署證據。Drive：待本人網頁上傳至實驗室帳號 XiaoZhao/ApprovedSource，下載核對前不算驗證通過。\n')
    note_path='docs/handover/LM_更新摘要_安全分支同步_20261108.md'
    paths=git(repo,'ls-tree','-r','--name-only','-z',commit).decode().split('\0')
    note=git(repo,'show',f'{commit}:{note_path}').decode() if note_path in paths else '# 待交給 LM\n\n請本人先審閱此版本程式與架構變更，不提供憑證、個資或資料庫。\n'
    note=f'版本 Commit：`{commit}`\n\n'+note
    for text in [version,note]:scan_content('docs/handover/release.md',text.encode())
    write_once(out/(name+'.sha256'),(digest+'  '+name+'\n').encode())
    write_once(out/f'VERSION_{commit[:12]}.md',version.encode())
    write_once(out/f'LM_{commit[:12]}.md',note.encode())
    return {'bundlePath':str(out),'zipSha256':digest,'sourceFiles':info['files'],'driveStatus':'pending_manual_upload'}

def publish(job,*,protected_repo,artifacts,expected_remote=REMOTE,check_only=False):
    repo=Path(job['repoPath']).resolve();commit=job['approvedCommit'];tag=job['stableTag'];base=job['reviewedBaseCommit'];base_ref=job['reviewedBaseRef']
    if repo==Path(protected_repo).resolve():raise PermissionError('PROTECTED_MAIN_WORKSPACE')
    if not all(re.fullmatch(r'[a-f0-9]{40}',s) for s in [commit,base]):raise ValueError('FULL_PINNED_SHA_REQUIRED')
    if not re.fullmatch(r'stable-ready-[A-Za-z0-9_-]{1,100}',tag):raise ValueError('EXACT_STABLE_TAG_REQUIRED')
    if not re.fullmatch(r'refs/heads/sync/[A-Za-z0-9/_-]{1,100}',base_ref) or '..' in base_ref:raise ValueError('REVIEWED_BASE_REF_REQUIRED')
    if git(repo,'remote','get-url','origin').decode().strip()!=expected_remote:raise PermissionError('WRONG_ORIGIN')
    if git(repo,'status','--porcelain','--untracked-files=no').strip():raise Skip('TRACKED_DIRTY_NO_PUSH')
    if git(repo,'branch','--show-current').decode().strip()!=job['sourceBranch']:raise Skip('SOURCE_BRANCH_CHANGED_NO_PUSH')
    if git(repo,'rev-parse','HEAD').decode().strip()!=commit:raise Skip('HEAD_NOT_APPROVED_NO_PUSH')
    if git(repo,'cat-file','-t','refs/tags/'+tag).decode().strip()!='commit':raise PermissionError('LIGHTWEIGHT_COMMIT_TAG_REQUIRED')
    if git(repo,'rev-parse','refs/tags/'+tag).decode().strip()!=commit:raise PermissionError('TAG_SHA_MISMATCH')
    if remote_sha(repo,base_ref)!=base:raise PermissionError('REVIEWED_REMOTE_BASE_CHANGED')
    git(repo,'merge-base','--is-ancestor',base,commit)
    receipt=json.loads(git(repo,'show',f'{commit}:{RECEIPT}'))
    if any(receipt.get(k)!='PASS' for k in ['backend','typescript','frontend','sensitiveReview']) or receipt.get('sourceDigest')!=source_digest(repo,commit):
        raise PermissionError('TESTED_SOURCE_RECEIPT_MISSING_OR_STALE')
    # Review ALL introduced history, including secrets later removed at HEAD.
    commits=git(repo,'rev-list',commit,'^'+base).decode().splitlines()
    for revision in commits:
        names=git(repo,'diff-tree','--root','-r','-m','--name-only','--no-commit-id','-z',revision).decode().split('\0')
        existing=set(git(repo,'ls-tree','-r','--name-only','-z',revision).decode().split('\0'))
        for path in set(names)-{''}:
            if path!=RECEIPT and not eligible(path):raise PermissionError('UNREVIEWED_PATH_IN_NEW_HISTORY')
            if path in existing:scan_content(path,git(repo,'show',f'{revision}:{path}'))
    branch='refs/heads/sync/approved-'+commit[:12];tag_ref='refs/tags/'+tag
    before=remote_sha(repo,branch);remote_tag=remote_sha(repo,tag_ref)
    if before not in [None,commit] or remote_tag not in [None,commit]:raise PermissionError('REMOTE_REF_CONFLICT_NO_OVERWRITE')
    package=bundle(repo,commit,artifacts,receipt)  # scan before any remote mutation
    if check_only:return dict(package,status='check_only_no_push',remoteVerified=False,commit=commit)
    if git(repo,'status','--porcelain','--untracked-files=no').strip() or git(repo,'rev-parse','HEAD').decode().strip()!=commit:raise Skip('SOURCE_CHANGED_NO_PUSH')
    if before is None or remote_tag is None:
        git(repo,'push','--atomic','origin',commit+':'+branch,'refs/tags/'+tag+':'+tag_ref)
    if remote_sha(repo,branch)!=commit or remote_sha(repo,tag_ref)!=commit:raise RuntimeError('REMOTE_COMMIT_NOT_VERIFIED')
    return dict(package,status='verified_existing' if before==commit and remote_tag==commit else 'pushed_verified',remoteVerified=True,commit=commit,branch=branch,stableTag=tag)

def run_queue(cfg,state,*,check_only=False):
    state=Path(state);state.mkdir(parents=True,exist_ok=True);lock=state/'publisher.lock';held=False
    def log(event):
        with (state/'github-approved-sync.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps(dict(timeUTC=datetime.now(timezone.utc).isoformat(),**event),ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
    try:
        with lock.open('x') as f:f.write(str(os.getpid()))
        held=True
        if cfg.get('enabled') is not True or not cfg.get('jobs'):raise Skip('DISABLED_OR_EMPTY_APPROVED_QUEUE')
        results=[]
        for job in cfg['jobs']:
            try:
                result=publish(job,protected_repo=cfg['protectedRepo'],artifacts=state/'manual-upload',check_only=check_only)
                log(result);results.append(result)
            except Skip as exc:
                result={'status':'skip','reason':str(exc),'remoteVerified':False};log(result);results.append(result)
            except Exception as exc:
                log({'status':'blocked','errorType':type(exc).__name__,'remoteVerified':False});return 1
        return 0 if all(r.get('remoteVerified') for r in results) else 2
    except Skip as exc:log({'status':'skip','reason':str(exc),'remoteVerified':False});return 2
    except Exception as exc:log({'status':'blocked','errorType':type(exc).__name__,'remoteVerified':False});return 1
    finally:
        if held:lock.unlink()

def verify_github_access():
    user=subprocess.run(['gh','api','user','--jq','.login'],capture_output=True,timeout=30)
    if user.returncode or user.stdout.decode().strip()!='icnclab':raise PermissionError('LAB_GITHUB_ACCOUNT_REQUIRED')
    repo=subprocess.run(['gh','api','repos/icnclab/xiaozhao-jiaan-1030','--jq','.private and .permissions.push'],capture_output=True,timeout=30)
    if repo.returncode or repo.stdout.decode().strip()!='true':raise PermissionError('PRIVATE_REPO_PUSH_ACCESS_REQUIRED')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True);p.add_argument('--state',required=True);p.add_argument('--check-only',action='store_true');a=p.parse_args()
    cfg=json.loads(Path(a.config).read_text(encoding='utf-8-sig'))
    if not a.check_only:verify_github_access()
    return run_queue(cfg,a.state,check_only=a.check_only)

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print('APPROVED_SYNC_BLOCKED: '+type(exc).__name__);raise SystemExit(1)

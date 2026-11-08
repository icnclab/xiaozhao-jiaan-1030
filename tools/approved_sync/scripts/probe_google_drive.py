"""One synthetic-file probe after human OAuth/Picker; no automatic upload retry."""
import argparse,hashlib,io,json,logging,os,re,secrets
from datetime import datetime,timezone
from pathlib import Path
from google_drive_api import GoogleDriveBackup,authenticated_service

BASE_COMMIT='78ff63e9041243125e785e661f45c7f11fe3bcab'

def run_probe(cfg,private_dir,*,service,credentials,http):
    if cfg.get('driveEnabled') is not False or cfg.get('driveAccountCheckedByHuman') is not True or cfg.get('pickerGrantVerified') is not True:
        raise PermissionError('HUMAN_AND_PICKER_CHECK_REQUIRED_SYNC_MUST_REMAIN_DISABLED')
    client=GoogleDriveBackup(cfg,service=service,read_only=True)
    private_dir=Path(private_dir);private_dir.mkdir(parents=True,exist_ok=True)
    marker=private_dir/'drive-probe.once.json';log=private_dir/'drive-probe.jsonl'
    run=secrets.token_hex(12)
    payload=json.dumps({'purpose':'XiaoZhao synthetic backup connectivity test',
                        'synthetic':True,'run':run},sort_keys=True).encode('utf-8')
    digest=hashlib.sha256(payload).hexdigest()
    record={'run':run,'referenceCommit':BASE_COMMIT,'sha256':digest,'status':'started',
            'time':datetime.now(timezone.utc).isoformat(),'cloudVerified':False,'postCalls':0}
    # Exclusive, durable marker is created BEFORE a possible network write. It is
    # retained on every failure, including an uncertain timeout. Never auto-clear.
    with marker.open('x',encoding='utf-8') as f:
        json.dump(record,f);f.flush();os.fsync(f.fileno())
    def append():
        with log.open('a',encoding='utf-8') as f:
            f.write(json.dumps(record,sort_keys=True)+'\n');f.flush();os.fsync(f.fileno())
    append()
    try:
        name='xiaozhao_synthetic_probe_'+run+'.txt'
        metadata=json.dumps({'name':name,'parents':[client.folder],
            'appProperties':{'backup_kind':'xiaozhao-synthetic-probe-v1','probe_run':run}}).encode()
        boundary='xiaozhao_'+run
        body=(b'--'+boundary.encode()+b'\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'+metadata+
              b'\r\n--'+boundary.encode()+b'\r\nContent-Type: text/plain; charset=UTF-8\r\n\r\n'+payload+
              b'\r\n--'+boundary.encode()+b'--\r\n')
        headers={'Authorization':'Bearer '+credentials.token,'Content-Type':'multipart/related; boundary='+boundary}
        record['postCalls']=1;record['status']='upload_attempted';append()
        # requests session below has no auth-refresh retry, retry adapter or
        # redirects. An ambiguous response must be reconciled read-only by a human.
        response=http.post('https://www.googleapis.com/upload/drive/v3/files',
            params={'uploadType':'multipart','fields':'id'},headers=headers,data=body,timeout=30,allow_redirects=False)
        if response.status_code!=200:raise IOError('UPLOAD_FAILED_NO_RETRY')
        file_id=response.json()['id']
        if not isinstance(file_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,200}',file_id):raise ValueError('BAD_FILE_ID')
        record['fileId']=file_id;record['status']='uploaded_not_verified';append()
        info=service.files().get(fileId=file_id,fields='id,name,parents,trashed,size,appProperties').execute(num_retries=0)
        if info.get('name')!=name or info.get('parents')!=[client.folder] or info.get('trashed') or int(info.get('size',-1))!=len(payload) or info.get('appProperties')!={'backup_kind':'xiaozhao-synthetic-probe-v1','probe_run':run}:
            raise IOError('UPLOADED_METADATA_MISMATCH')
        downloaded=http.get('https://www.googleapis.com/drive/v3/files/'+file_id,
            params={'alt':'media'},headers={'Authorization':'Bearer '+credentials.token},timeout=30,allow_redirects=False,stream=True)
        if downloaded.status_code!=200:raise IOError('DOWNLOAD_FAILED')
        buffer=io.BytesIO()
        for part in downloaded.iter_content(chunk_size=1024):
            buffer.write(part)
            if buffer.tell()>len(payload):raise IOError('DOWNLOAD_TOO_LARGE')
        actual=hashlib.sha256(buffer.getvalue()).hexdigest()
        if actual!=digest:raise IOError('DOWNLOADED_SHA256_MISMATCH')
        record.update(status='passed',downloadSha256=actual,probeVerified=True)
        # This synthetic test is NOT a verified source backup.
        append();return record
    except Exception as exc:
        record.update(status='failed_or_unknown_no_retry',errorType=type(exc).__name__)
        append();raise

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True)
    p.add_argument('--run-once',action='store_true');a=p.parse_args()
    if not a.run_once:
        print('CHECK ONLY: no network calls, OAuth refresh, upload or download');return
    config=Path(a.config).resolve();private=Path(os.environ['LOCALAPPDATA'])/'XiaoZhaoSync'
    if config!=(private/'sync_targets.local.json').resolve():raise PermissionError('DEDICATED_PRIVATE_CONFIG_REQUIRED')
    # Fail before token refresh if a previous attempt exists.
    if (private/'drive-probe.once.json').exists():raise FileExistsError('PREVIOUS_ATTEMPT_REQUIRES_MANUAL_RECONCILIATION')
    cfg=json.loads(config.read_text(encoding='utf-8-sig'))
    service,credentials=authenticated_service(cfg)
    import requests
    from requests.adapters import HTTPAdapter
    with requests.Session() as http:
        http.mount('https://',HTTPAdapter(max_retries=0))
        run_probe(cfg,private,service=service,credentials=credentials,http=http)
    print('PASS: one synthetic file uploaded and downloaded; SHA256 matched; schedule remains disabled')

if __name__=='__main__':
    logging.disable(logging.CRITICAL)
    try:main()
    except Exception as exc:
        print('PROBE_BLOCKED_NO_RETRY: '+type(exc).__name__);raise SystemExit(1)

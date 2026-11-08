"""Manual-only installed-app OAuth. No consent is started without --authorize.
Credentials stay under LOCALAPPDATA/XiaoZhaoSync/oauth, outside any Git repo.
"""
import argparse,json,logging,os,secrets,subprocess,sys
from pathlib import Path
from google_drive_api import GoogleDriveBackup,SCOPE,expected_account

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True)
    p.add_argument('--authorize',action='store_true');p.add_argument('--check-identity',action='store_true');a=p.parse_args()
    cfg=json.loads(Path(a.config).read_text(encoding='utf-8-sig'))
    account=expected_account(cfg)
    if not a.authorize and not a.check_identity:
        print('CHECK ONLY: no OAuth browser, listener, token refresh or upload started');return 0
    if a.authorize:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        target=Path(cfg['oauthTokenFile']).resolve()
        allowed=(Path(os.environ['LOCALAPPDATA'])/'XiaoZhaoSync/oauth').resolve()
        if target.parent!=allowed or target.exists():raise PermissionError('NEW_PRIVATE_OAUTH_TOKEN_PATH_REQUIRED')
        allowed.mkdir(parents=True,exist_ok=True)
        if os.name=='nt':
            # Restrict the dedicated OAuth folder, not any ancestor or repository.
            owner=subprocess.run(['whoami','/user','/fo','csv','/nh'],capture_output=True,text=True,check=True).stdout.strip().split(',')[-1].strip('"')
            subprocess.run(['icacls',str(allowed),'/inheritance:r','/grant:r',f'*{owner}:(OI)(CI)F','*S-1-5-18:(OI)(CI)F'],capture_output=True,check=True)
        else:allowed.chmod(0o700)
        previous=logging.root.manager.disable;logging.disable(logging.CRITICAL)
        try:
            flow=InstalledAppFlow.from_client_secrets_file(cfg['oauthClientFile'],scopes=[SCOPE],autogenerate_code_verifier=True)
            credentials=flow.run_local_server(host='127.0.0.1',port=0,open_browser=True,timeout_seconds=300,access_type='offline',prompt='consent',login_hint=account,include_granted_scopes='false',authorization_prompt_message='請由本人在瀏覽器確認實驗室帳號與授權。',success_message='授權回應已收到，請回到本機工具查看核對結果。')
            if not credentials.refresh_token or set(credentials.granted_scopes or credentials.scopes or [])!={SCOPE}:
                raise PermissionError('EXACT_DRIVE_FILE_AND_REFRESH_TOKEN_REQUIRED')
            service=build('drive','v3',credentials=credentials,cache_discovery=False)
            user=service.about().get(fields='user(emailAddress,me)').execute()['user']
            if user.get('emailAddress','').lower()!=account or user.get('me') is not True:raise PermissionError('WRONG_GOOGLE_ACCOUNT_TOKEN_NOT_SAVED')
            with target.open('x',encoding='utf-8') as f:f.write(credentials.to_json())
            if os.name!='nt':target.chmod(0o600)
        finally:logging.disable(previous)
        print('OAuth completed by user; expected account verified; private token saved; uploads still disabled')
    if a.check_identity:
        GoogleDriveBackup(cfg,read_only=True)
        print('PASS: authenticated lab account, owned XiaoZhao/ApprovedSource folder IDs and write capability; NO upload performed')
    return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print('OAUTH_SETUP_BLOCKED: '+type(exc).__name__,file=sys.stderr);raise SystemExit(1)

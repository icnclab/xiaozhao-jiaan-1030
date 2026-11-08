"""Google Drive v3 only; no desktop client, rclone, OneDrive or implicit OAuth.
Dependencies are lazy: install in a separate backup-tools environment, not the
shared application venv. This module never starts an OAuth consent flow itself.
"""
import hashlib,io,re
from pathlib import Path

SCOPE='https://www.googleapis.com/auth/drive.file'
def expected_account(cfg):
    account=cfg.get('expectedDriveAccount','').strip().lower()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',account):raise ValueError('LAB_ACCOUNT_PRIVATE_CONFIG_REQUIRED')
    return account

class GoogleDriveBackup:
    def __init__(self,cfg,*,service=None,media_factory=None,read_only=False):
        self.upload_enabled=not read_only and cfg.get('driveEnabled') is True and cfg.get('driveAccountCheckedByHuman') is True
        if not read_only and not self.upload_enabled:
            raise PermissionError('DRIVE_NOT_APPROVED')
        account=expected_account(cfg)
        self.folder=cfg.get('driveFolderId','');self.parent=cfg.get('driveParentFolderId','')
        if not all(re.fullmatch(r'[A-Za-z0-9_-]{8,200}',x) for x in [self.folder,self.parent]):
            raise ValueError('DRIVE_FOLDER_IDS_REQUIRED')
        if service is None:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
            token=Path(cfg['oauthTokenFile']).resolve()
            if token.is_relative_to(Path(cfg['repoPath']).resolve()):raise PermissionError('OAUTH_TOKEN_MUST_BE_OUTSIDE_REPOSITORY')
            credentials=Credentials.from_authorized_user_file(str(token))
            if set(credentials.scopes or [])!={SCOPE}:raise PermissionError('UNEXPECTED_OAUTH_SCOPES')
            if not credentials.valid:
                if not credentials.refresh_token:raise PermissionError('USER_OAUTH_REQUIRED')
                credentials.refresh(Request())
            # google-auth can refresh in memory; do not log credentials or rewrite
            # OAuth files without the explicit authorization setup command.
            service=build('drive','v3',credentials=credentials,cache_discovery=False)
        self.service=service;self.media_factory=media_factory
        user=service.about().get(fields='user(emailAddress,me)').execute()['user']
        if user.get('emailAddress','').lower()!=account or user.get('me') is not True:
            raise PermissionError('AUTHENTICATED_DRIVE_ACCOUNT_MISMATCH')
        for file_id,name in [(self.parent,'XiaoZhao'),(self.folder,'ApprovedSource')]:
            item=service.files().get(fileId=file_id,fields='id,name,mimeType,trashed,ownedByMe,driveId,parents,capabilities(canAddChildren)').execute()
            if item.get('id')!=file_id or item.get('name')!=name or item.get('mimeType')!='application/vnd.google-apps.folder' or item.get('trashed') or item.get('ownedByMe') is not True or item.get('driveId') or item.get('capabilities',{}).get('canAddChildren') is not True:
                raise PermissionError('DRIVE_FOLDER_IDENTITY_OR_PERMISSION_MISMATCH')
            if file_id==self.folder and item.get('parents')!=[self.parent]:raise PermissionError('DRIVE_FOLDER_PARENT_MISMATCH')

    def upload_verified(self,path,commit):
        if not self.upload_enabled:raise PermissionError('READ_ONLY_IDENTITY_CHECK_NO_UPLOAD')
        path=Path(path)
        if not re.fullmatch(r'[a-f0-9]{40}',commit):raise ValueError('FULL_COMMIT_REQUIRED')
        if path.name not in {f'xiaozhao_code_{commit[:12]}.zip',f'待交給LM學習_{commit[:12]}.md'}:raise ValueError('ONLY_VERSIONED_APPROVED_ARTIFACTS')
        content=path.read_bytes();checksum=hashlib.md5(content,usedforsecurity=False).hexdigest()
        name=path.name.replace('\\','\\\\').replace("'","\\'")
        existing=self.service.files().list(q=f"'{self.folder}' in parents and name='{name}' and trashed=false",fields='nextPageToken,files(id)',pageSize=100).execute()
        if existing.get('nextPageToken') or len(existing.get('files',[]))>1:raise FileExistsError('AMBIGUOUS_EXISTING_VERSION')
        files=existing.get('files',[])
        if files:file_id=files[0]['id']
        else:
            factory=self.media_factory
            if factory is None:
                from googleapiclient.http import MediaIoBaseUpload
                factory=MediaIoBaseUpload
            media=factory(io.BytesIO(content),mimetype='application/zip' if path.suffix=='.zip' else 'text/markdown',chunksize=1024*1024,resumable=True)
            request=self.service.files().create(body={'name':path.name,'parents':[self.folder],'appProperties':{'source_commit':commit,'backup_kind':'xiaozhao-approved-source-v1'}},media_body=media,fields='id')
            response=None
            while response is None:_,response=request.next_chunk(num_retries=0)
            file_id=response['id']
        info=self.service.files().get(fileId=file_id,fields='id,name,parents,size,md5Checksum,appProperties,trashed').execute()
        if info.get('name')!=path.name or info.get('parents')!=[self.folder] or info.get('trashed') or info.get('md5Checksum')!=checksum or int(info.get('size',-1))!=len(content) or info.get('appProperties',{}).get('source_commit')!=commit or info.get('appProperties',{}).get('backup_kind')!='xiaozhao-approved-source-v1':
            raise IOError('DRIVE_REMOTE_CHECKSUM_OR_VERSION_MISMATCH')
        return {'fileId':file_id,'remoteMd5Verified':True,'sha256':hashlib.sha256(content).hexdigest()}

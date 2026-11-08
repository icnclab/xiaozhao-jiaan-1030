import hashlib,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from google_drive_api import GoogleDriveBackup

class DriveTests(unittest.TestCase):
    def setUp(self):
        self.cfg={'driveEnabled':True,'driveAccountCheckedByHuman':True,'expectedDriveAccount':'lab@example.test','driveFolderId':'approved-source-123','driveParentFolderId':'xiaozhao-parent-123'}
        self.service=MagicMock();self.service.about().get().execute.return_value={'user':{'emailAddress':'lab@example.test','me':True}}
        self.commit='a'*40;self.data=b'synthetic reviewed source only'
        self.service.files().get.side_effect=self.get
        self.service.files().list().execute.return_value={'files':[]}
        self.service.files().create().next_chunk.return_value=(None,{'id':'file-123'})
        self.service.files().create.reset_mock()
    def get(self,*,fileId,**kwargs):
        response=MagicMock()
        if fileId in ['approved-source-123','xiaozhao-parent-123']:
            d={'id':fileId,'name':'ApprovedSource' if fileId.startswith('approved') else 'XiaoZhao','mimeType':'application/vnd.google-apps.folder','ownedByMe':True,'trashed':False,'capabilities':{'canAddChildren':True}}
            if fileId.startswith('approved'):d['parents']=['xiaozhao-parent-123']
        else:d={'id':fileId,'name':'xiaozhao_code_'+self.commit[:12]+'.zip','parents':['approved-source-123'],'size':str(len(self.data)),'md5Checksum':hashlib.md5(self.data).hexdigest(),'appProperties':{'source_commit':self.commit,'backup_kind':'xiaozhao-approved-source-v1'}}
        response.execute.return_value=d;return response
    def client(self,**kwargs):return GoogleDriveBackup(self.cfg,service=self.service,media_factory=MagicMock(),**kwargs)
    def artifact(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);p=Path(t.name)/('xiaozhao_code_'+self.commit[:12]+'.zip');p.write_bytes(self.data);return p
    def test_remote_checksum_and_version(self):
        result=self.client().upload_verified(self.artifact(),self.commit)
        self.assertTrue(result['remoteMd5Verified'])
        self.assertEqual(self.service.files().create.call_args.kwargs['body']['parents'],['approved-source-123'])
    def test_disabled_no_api_upload(self):
        self.cfg['driveEnabled']=False
        with self.assertRaises(PermissionError):self.client()
    def test_wrong_account_denies_before_files(self):
        self.service.about().get().execute.return_value={'user':{'emailAddress':'wrong@example.invalid','me':True}}
        with self.assertRaises(PermissionError):self.client()
        self.service.files().create.assert_not_called()
    def test_wrong_parent_denies(self):
        self.cfg['driveParentFolderId']='different-parent-123'
        with self.assertRaises(PermissionError):self.client()
    def test_readonly_identity_never_uploads(self):
        self.cfg['driveEnabled']=False;self.cfg['driveAccountCheckedByHuman']=False;c=self.client(read_only=True)
        with self.assertRaises(PermissionError):c.upload_verified(self.artifact(),self.commit)
    def test_checksum_failure_not_success(self):
        c=self.client();p=self.artifact();self.data=b'different remote bytes'
        with self.assertRaises(IOError):c.upload_verified(p,self.commit)
    def test_duplicate_remote_version_denies(self):
        c=self.client();self.service.files().list().execute.return_value={'files':[{'id':'a'},{'id':'b'}]}
        with self.assertRaises(FileExistsError):c.upload_verified(self.artifact(),self.commit)
    def test_arbitrary_private_path_not_uploaded(self):
        c=self.client()
        with self.assertRaises(ValueError):c.upload_verified(Path('uat.local.env'),self.commit)

if __name__=='__main__':unittest.main()

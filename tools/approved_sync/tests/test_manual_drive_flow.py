import json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from picker_google_drive import validated_selection,render_page
from probe_google_drive import run_probe

class ManualFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.cfg={'driveEnabled':False,'driveAccountCheckedByHuman':True,'pickerGrantVerified':True,
                  'expectedDriveAccount':'lab@example.test','driveFolderId':'approved-source-123',
                  'driveParentFolderId':'xiaozhao-parent-123'}
        self.service=MagicMock();self.http=MagicMock();self.credentials=SimpleNamespace(token='mock-only')
        self.service.about().get().execute.return_value={'user':{'emailAddress':'lab@example.test','me':True}}
        self.info={};self.content=b''
        def get(*,fileId,**kwargs):
            if fileId=='synthetic-file-123':d=self.info
            else:
                d={'id':fileId,'name':'ApprovedSource' if fileId=='approved-source-123' else 'XiaoZhao',
                   'mimeType':'application/vnd.google-apps.folder','ownedByMe':True,
                   'capabilities':{'canAddChildren':True}}
                if fileId=='approved-source-123':d['parents']=['xiaozhao-parent-123']
            response=MagicMock();response.execute.return_value=d;return response
        self.service.files().get.side_effect=get
        def post(url,**kwargs):
            parts=kwargs['data'].split(b'\r\n\r\n')
            self.info=json.loads(parts[1].split(b'\r\n--')[0]);self.info['id']='synthetic-file-123'
            self.content=parts[2].split(b'\r\n--')[0];self.info['size']=str(len(self.content))
            r=MagicMock(status_code=200);r.json.return_value={'id':'synthetic-file-123'};return r
        self.http.post.side_effect=post
        def download(*args,**kwargs):
            return SimpleNamespace(status_code=200,iter_content=lambda **kw:iter([self.content]))
        self.http.get.side_effect=download
    def run_probe(self):
        return run_probe(self.cfg,self.tmp.name,service=self.service,credentials=self.credentials,http=self.http)
    def test_round_trip_matches_sha_logs_no_token(self):
        r=self.run_probe();self.assertTrue(r['probeVerified']);self.assertFalse(r['cloudVerified'])
        self.assertEqual(r['sha256'],r['downloadSha256']);self.http.post.assert_called_once()
        self.assertFalse(self.http.post.call_args.kwargs['allow_redirects'])
        logs=(Path(self.tmp.name)/'drive-probe.jsonl').read_text()
        self.assertNotIn('mock-only',logs);self.assertIn('passed',logs)
    def test_second_invocation_never_uploads(self):
        self.run_probe()
        with self.assertRaises(FileExistsError):self.run_probe()
        self.http.post.assert_called_once()
    def test_timeout_is_unknown_and_not_retried(self):
        self.http.post.side_effect=TimeoutError('sensitive server response must not be logged')
        with self.assertRaises(TimeoutError):self.run_probe()
        with self.assertRaises(FileExistsError):self.run_probe()
        self.http.post.assert_called_once()
        logs=(Path(self.tmp.name)/'drive-probe.jsonl').read_text()
        self.assertIn('failed_or_unknown_no_retry',logs);self.assertNotIn('sensitive server',logs)
    def test_download_corruption_is_not_pass(self):
        self.http.get.side_effect=lambda *a,**kw:SimpleNamespace(status_code=200,iter_content=lambda **kw:iter([b'bad']))
        with self.assertRaises(IOError):self.run_probe()
        self.assertNotIn('"status": "passed"',(Path(self.tmp.name)/'drive-probe.jsonl').read_text())
        self.http.post.assert_called_once()
    def test_http_error_no_download_or_retry(self):
        self.http.post.side_effect=None;self.http.post.return_value=SimpleNamespace(status_code=403)
        with self.assertRaises(IOError):self.run_probe()
        self.http.post.assert_called_once();self.http.get.assert_not_called()
    def test_wrong_account_no_upload(self):
        self.service.about().get().execute.return_value={'user':{'emailAddress':'wrong@example.test','me':True}}
        with self.assertRaises(PermissionError):self.run_probe()
        self.http.post.assert_not_called()
    def test_missing_human_or_picker_no_upload(self):
        for field in ['driveAccountCheckedByHuman','pickerGrantVerified']:
            cfg=dict(self.cfg);cfg[field]=False
            with self.assertRaises(PermissionError):run_probe(cfg,self.tmp.name,service=self.service,credentials=self.credentials,http=self.http)
        self.http.post.assert_not_called()
    def test_picker_never_enables_sync(self):
        r=validated_selection(self.cfg,{'parent':'xiaozhao-parent-123','folder':'approved-source-123'},self.service)
        self.assertFalse(r['driveEnabled']);self.assertFalse(r['driveAccountCheckedByHuman']);self.assertTrue(r['pickerGrantVerified'])
        self.service.files().create.assert_not_called()
    def test_wrong_folder_relationship_denied(self):
        with self.assertRaises(PermissionError):validated_selection(self.cfg,{'parent':'different-parent-123','folder':'approved-source-123'},self.service)
        self.service.files().create.assert_not_called()
    def test_picker_page_escapes_script_data(self):
        page=render_page('fake-key','123456789','</script>','nonce')
        self.assertNotIn('"token": "</script>"',page)
        self.assertIn('setSelectFolderEnabled(true)',page);self.assertIn('setOAuthToken',page)
    def test_picker_malformed_selection_no_api(self):
        for payload in [None,[],{'parent':4,'folder':'approved-source-123'},{'parent':'xiaozhao-parent-123'}]:
            with self.assertRaises(ValueError):validated_selection(self.cfg,payload,self.service)
        self.service.files().create.assert_not_called()
    def test_metadata_mismatch_does_not_download(self):
        original=self.http.post.side_effect
        def wrong_parent(*args,**kwargs):
            response=original(*args,**kwargs);self.info['parents']=['wrong-folder-123'];return response
        self.http.post.side_effect=wrong_parent
        with self.assertRaises(IOError):self.run_probe()
        self.http.post.assert_called_once();self.http.get.assert_not_called()

if __name__=='__main__':unittest.main()

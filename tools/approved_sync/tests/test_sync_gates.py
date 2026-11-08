import json,os,sys,tempfile,unittest,secrets
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import sync_verified as sync
from export_approved_snapshot import scan_content

class GateTests(unittest.TestCase):
    def test_reviewed_synthetic_file_hash_cannot_cover_changed_content(self):
        repo=Path(__file__).resolve().parents[3]
        path='backend/tests/test_deid.py';content=(repo/path).read_bytes()
        scan_content(path,content)
        with self.assertRaises(ValueError):scan_content(path,content+b'\n# changed source invalidates approval\n')
    def test_real_literal_password_still_blocked(self):
        # Manufacture a secret-looking value for this test only, never store one.
        content=('DATABASE_URL="postgresql'+f'://unit_user:{secrets.token_hex(24)}@synthetic.invalid/unit"').encode()
        with self.assertRaises(ValueError):scan_content('backend/app/new.py',content)
    def test_remote_tag_required_before_drive(self):
        with patch.object(sync,'run',return_value=SimpleNamespace(stdout='')):
            with self.assertRaises(PermissionError):sync.verify_quality_gate(Path('.'),'a'*40)
    def test_stale_tested_source_receipt_rejected(self):
        receipt={'sourceDigest':'old','backend':'PASS','typescript':'PASS','frontend':'PASS','sensitiveReview':'PASS'}
        with patch.object(sync,'run',return_value=SimpleNamespace(stdout='a'*40+' refs/tags/stable-ready-test')),patch.object(sync,'git_bytes',return_value=json.dumps(receipt).encode()),patch.object(sync,'source_digest',return_value='new'):
            with self.assertRaises(PermissionError):sync.verify_quality_gate(Path('.'),'a'*40)
    def test_failed_test_receipt_rejected(self):
        receipt={'sourceDigest':'same','backend':'FAIL','typescript':'PASS','frontend':'PASS','sensitiveReview':'PASS'}
        with patch.object(sync,'run',return_value=SimpleNamespace(stdout='a'*40+' refs/tags/stable-ready-test')),patch.object(sync,'git_bytes',return_value=json.dumps(receipt).encode()):
            with self.assertRaises(PermissionError):sync.verify_quality_gate(Path('.'),'a'*40)
    def test_concurrent_cli_blocked_without_deleting_owner_lock(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'LOCALAPPDATA':temp}),patch.object(sys,'argv',['sync_verified','--config','unused.json']),patch.object(sync,'sync') as action:
            root=Path(temp)/'XiaoZhaoSync';root.mkdir();lock=root/'approved-sync.lock';lock.write_text('another process')
            self.assertEqual(sync.main(),1);action.assert_not_called();self.assertEqual(lock.read_text(),'another process')
            records=[json.loads(x) for x in (root/'logs/dual_sync.jsonl').read_text().splitlines()]
            self.assertEqual(records[-1]['result'],'blocked')

if __name__=='__main__':unittest.main()

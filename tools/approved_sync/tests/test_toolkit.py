import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from export_approved_snapshot import export
from sync_verified import sync, source_digest


def command(*args, cwd=None):
    p = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if p.returncode:
        raise RuntimeError(f'cmd exit {p.returncode}: {args[:2]}, {p.stderr[-600:]}')
    return p.stdout.strip()


class ToolkitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        # Even mock uploads must never write to the user's real backup staging.
        environment=patch.dict(os.environ,{'LOCALAPPDATA':str(self.base/'mock-appdata')})
        environment.start();self.addCleanup(environment.stop)
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        command('git', 'init', '-q', str(self.repo))
        command('git', '-C', str(self.repo), 'config', 'user.name', 'Test Only')
        command('git', '-C', str(self.repo), 'config', 'user.email', 'test@example.invalid')
        self.put('backend/app/main.py', 'print("hello")\n')
        self.put('frontend/src/app.tsx', 'export const app = true;\n')
        self.put('docs/uat/00.md', '# test-only UAT\n')
        self.put('docs/interviews/raw.txt', 'THIS IS PRIVATE TEST CONTENT\n')
        self.put('.env', 'LINE_CHANNEL_SECRET=fake-secret\n')
        self.put('data_demo/example.json', '{"name": "private"}\n')
        command('git', '-C', str(self.repo), 'add', '--', 'backend', 'frontend', 'docs', '.env', 'data_demo')
        command('git', '-C', str(self.repo), 'commit', '-qm', 'fixture')
        self.head = command('git', '-C', str(self.repo), 'rev-parse', 'HEAD')

    def put(self, name, value):
        dest = self.repo / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(value, encoding='utf-8')

    def test_archive_filters_private_data_and_is_reproducible(self):
        a = self.base / 'a.zip'
        b = self.base / 'b.zip'
        report = export(self.repo, self.head, a)
        export(self.repo, self.head, b)
        self.assertEqual(a.read_bytes(), b.read_bytes())
        with zipfile.ZipFile(a) as z:
            names = z.namelist()
            self.assertIn('backend/app/main.py', names)
            self.assertIn('frontend/src/app.tsx', names)
            self.assertIn('docs/uat/00.md', names)
            self.assertNotIn('docs/interviews/raw.txt', names)
            self.assertNotIn('.env', names)
            self.assertNotIn('data_demo/example.json', names)
            manifest = json.loads(z.read('_snapshot_manifest.json'))
            self.assertEqual(manifest['source_commit'], self.head)
        self.assertEqual(report['files'], 3)

    def test_secret_rule_blocks_export(self):
        self.put('backend/app/auth.py', 'LINE_CHANNEL_SECRET="' + ('A' * 36) + '"\n')
        command('git', '-C', str(self.repo), 'add', '--', 'backend/app/auth.py')
        command('git', '-C', str(self.repo), 'commit', '-qm', 'unsafe test fixture')
        head = command('git', '-C', str(self.repo), 'rev-parse', 'HEAD')
        with self.assertRaisesRegex(ValueError, 'Possible line_token_assignment'):
            export(self.repo, head, self.base / 'blocked.zip')

    def test_verified_remote_branch_to_mock_drive_api(self):
        branch = 'sync/stable-20261107-jiaan1030'
        receipt={'sourceDigest':source_digest(self.repo,self.head),'backend':'PASS','typescript':'PASS','frontend':'PASS','sensitiveReview':'PASS'}
        self.put('.claude/approved-sync-validation.json',json.dumps(receipt))
        command('git','-C',str(self.repo),'add','--','.claude/approved-sync-validation.json')
        command('git','-C',str(self.repo),'commit','-qm','test-only approval receipt')
        self.head=command('git','-C',str(self.repo),'rev-parse','HEAD')
        command('git','-C',str(self.repo),'tag','stable-ready-test-only')
        command('git', '-C', str(self.repo), 'branch', branch)
        bare = self.base / 'remote.git'
        command('git', 'init', '--bare', '-q', str(bare))
        command('git', '-C', str(self.repo), 'remote', 'add', 'origin', str(bare))
        command('git', '-C', str(self.repo), 'push', '--quiet', 'origin', branch, 'refs/tags/stable-ready-test-only')
        folder = self.base / 'FakeGoogleDrive_DoesNotUpload'
        folder.mkdir()
        cfg = {
            'repoPath': str(self.repo),
            'expectedGitHubRemote': str(bare),
            'expectedGitHubAccount': 'test-only',
            'stableBranch': branch,
            'allowGitHubAutoPush': False,
            'driveMode': 'api',
            'driveEnabled': True,
            'driveFolder': str(folder),
            'driveAccountCheckedByHuman': True,
        }
        chk = sync(cfg, check_only=True)
        self.assertEqual(chk['githubRemoteCommit'], self.head)
        self.assertEqual(list(folder.iterdir()), [])
        class FakeDrive:
            def __init__(self,cfg):pass
            def upload_verified(self,path,commit):
                dest=folder/Path(path).name
                if dest.exists():self_test.assertEqual(dest.read_bytes(),Path(path).read_bytes())
                else:dest.write_bytes(Path(path).read_bytes())
                return {'fileId':'test-only-'+Path(path).suffix,'remoteMd5Verified':True}
        self_test=self
        with patch('sync_verified.GoogleDriveBackup',FakeDrive):result = sync(cfg)
        self.assertEqual(result['githubRemoteCommit'], self.head)
        self.assertEqual(result['sourceFiles'], 3)
        self.assertEqual(result['cloudVerified'], True)
        files = list(folder.iterdir())
        self.assertEqual(len(files), 2)
        self.assertEqual(len([f for f in files if f.name.endswith('.zip')]), 1)
        self.assertEqual(len([f for f in files if f.name.endswith('.md')]), 1)
        with patch('sync_verified.GoogleDriveBackup',FakeDrive):sync(cfg)
        self.assertEqual(len(list(folder.iterdir())), 2)

    def test_handover_mpc_five_scenarios(self):
        proc = subprocess.run([sys.executable, str(ROOT / 'handover_review/mpc_core.py'), '--quiet-test'],
                              text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr[-1200:])
        self.assertIn('MPC_CORE_OK', proc.stdout)


if __name__ == '__main__':
    unittest.main()

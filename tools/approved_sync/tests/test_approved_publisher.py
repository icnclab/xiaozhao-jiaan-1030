import hashlib,json,os,secrets,subprocess,sys,tempfile,unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import publish_approved_branch as pub

class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.repo=self.root/'candidate';self.repo.mkdir();self.remote=self.root/'remote.git'
        self.call('init','-q');self.call('config','user.name','Synthetic Test');self.call('config','user.email','test@example.invalid')
        self.put('backend/app/synthetic.py','value=1\n');self.call('add','--','backend/app/synthetic.py');self.call('commit','-qm','reviewed fixture base')
        self.base=self.call('rev-parse','HEAD');subprocess.run(['git','init','--bare','-q',str(self.remote)],check=True,capture_output=True)
        self.call('remote','add','origin',str(self.remote));self.call('push','-q','origin','HEAD:refs/heads/sync/reviewed-base')
        self.call('switch','-qc','candidate');self.put('backend/app/synthetic.py','value=2\n');self.make_commit()
    def call(self,*args):return pub.git(self.repo,*args).decode().strip()
    def put(self,p,text):
        path=self.repo/p;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
    def make_commit(self):
        self.sequence=getattr(self,'sequence',10)+1
        self.put('backend/app/synthetic.py','value='+str(self.sequence)+'\n')
        receipt={'backend':'PASS','typescript':'PASS','frontend':'PASS','sensitiveReview':'PASS','sourceDigest':''}
        self.call('add','--','backend/app/synthetic.py');self.call('commit','-qm','synthetic source revision')
        receipt['sourceDigest']=pub.source_digest(self.repo,self.call('rev-parse','HEAD'))
        self.put(pub.RECEIPT,json.dumps(receipt));self.call('add','--',pub.RECEIPT);self.call('commit','-qm','synthetic tested receipt')
        self.commit=self.call('rev-parse','HEAD');self.tag='stable-ready-test-'+secrets.token_hex(4);self.call('tag',self.tag)
        self.job={'repoPath':str(self.repo),'approvedCommit':self.commit,'sourceBranch':'candidate','stableTag':self.tag,'reviewedBaseCommit':self.base,'reviewedBaseRef':'refs/heads/sync/reviewed-base'}
    def publish(self,**kwargs):return pub.publish(self.job,protected_repo=self.root/'protected',artifacts=self.root/'artifacts',expected_remote=str(self.remote),**kwargs)
    def test_push_and_four_artifacts_and_repeat_verified(self):
        result=self.publish();self.assertEqual(result['status'],'pushed_verified');self.assertTrue(result['remoteVerified'])
        self.assertEqual(pub.remote_sha(self.repo,result['branch']),self.commit)
        files=list(Path(result['bundlePath']).iterdir());self.assertEqual(len(files),4)
        z=next(p for p in files if p.suffix=='.zip');self.assertEqual(hashlib.sha256(z.read_bytes()).hexdigest(),result['zipSha256'])
        with patch.object(pub,'git',wraps=pub.git) as git:
            self.assertEqual(self.publish()['status'],'verified_existing')
            self.assertFalse(any('push' in call.args[1:] for call in git.call_args_list))
    def test_dirty_source_is_skip_not_success(self):
        self.put('backend/app/synthetic.py','dirty=1\n')
        with self.assertRaises(pub.Skip):self.publish()
        self.assertIsNone(pub.remote_sha(self.repo,'refs/heads/sync/approved-'+self.commit[:12]))
    def test_protected_main_workspace_denied(self):
        with self.assertRaises(PermissionError):pub.publish(self.job,protected_repo=self.repo,artifacts=self.root/'out',expected_remote=str(self.remote))
    def test_unapproved_new_head_is_skip(self):
        self.put('backend/app/synthetic.py','value=3\n');self.call('add','--','backend/app/synthetic.py');self.call('commit','-qm','not approved')
        with self.assertRaises(pub.Skip):self.publish()
    def test_stale_receipt_denied(self):
        self.put('backend/app/synthetic.py','value=4\n');self.call('add','--','backend/app/synthetic.py');self.call('commit','-qm','changed after testing')
        self.job['approvedCommit']=self.call('rev-parse','HEAD');self.job['stableTag']='stable-ready-stale';self.call('tag',self.job['stableTag'])
        with self.assertRaises(PermissionError):self.publish()
    def test_conflicting_remote_never_overwritten(self):
        branch='refs/heads/sync/approved-'+self.commit[:12];self.call('push','-q','origin',self.base+':'+branch)
        with self.assertRaises(PermissionError):self.publish()
        self.assertEqual(pub.remote_sha(self.repo,branch),self.base)
    def test_wrong_origin_denied(self):
        with self.assertRaises(PermissionError):pub.publish(self.job,protected_repo=self.root/'protected',artifacts=self.root/'out')
    def test_check_only_does_not_push(self):
        result=self.publish(check_only=True);self.assertFalse(result['remoteVerified']);self.assertEqual(result['status'],'check_only_no_push')
        self.assertIsNone(pub.remote_sha(self.repo,'refs/heads/sync/approved-'+self.commit[:12]))
    def test_removed_secret_in_history_still_denied(self):
        self.put('backend/app/leak.py','token="'+('ghp_'+secrets.token_hex(24))+'"\n');self.call('add','--','backend/app/leak.py');self.call('commit','-qm','unsafe historical fixture')
        self.call('rm','-q','backend/app/leak.py');self.call('commit','-qm','removed unsafe fixture');self.make_commit()
        with self.assertRaises(ValueError):self.publish()
    def test_private_path_in_history_denied(self):
        self.put('docs/interviews/fake.txt','synthetic only');self.call('add','--','docs/interviews/fake.txt');self.call('commit','-qm','unreviewed path fixture');self.make_commit()
        with self.assertRaises(PermissionError):self.publish()
    def test_remote_mismatch_after_push_never_reports_success(self):
        actual=pub.remote_sha;seen={'count':0}
        def mismatch(repo,ref):
            if ref.startswith('refs/heads/sync/approved-'):
                seen['count']+=1
                if seen['count']>1:return self.base
            return actual(repo,ref)
        with patch.object(pub,'remote_sha',side_effect=mismatch):
            with self.assertRaises(RuntimeError):self.publish()
    def test_lock_is_not_deleted_by_competing_process(self):
        state=self.root/'state';state.mkdir();(state/'publisher.lock').write_text('other owner')
        self.assertEqual(pub.run_queue({'enabled':True,'jobs':[self.job]},state),1)
        self.assertEqual((state/'publisher.lock').read_text(),'other owner')
    def test_disabled_queue_is_skip_exit_two(self):
        state=self.root/'state';self.assertEqual(pub.run_queue({'enabled':False},state),2)
        last=json.loads((state/'github-approved-sync.jsonl').read_text().splitlines()[-1]);self.assertEqual(last['status'],'skip');self.assertFalse(last['remoteVerified'])

class GitHubAccessTests(unittest.TestCase):
    def test_wrong_account_blocks(self):
        with patch.object(pub.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=b'other-user')):
            with self.assertRaises(PermissionError):pub.verify_github_access()
    def test_public_repo_or_missing_push_permission_blocks(self):
        with patch.object(pub.subprocess,'run',side_effect=[SimpleNamespace(returncode=0,stdout=b'icnclab'),SimpleNamespace(returncode=0,stdout=b'false')]):
            with self.assertRaises(PermissionError):pub.verify_github_access()
    def test_private_repo_and_lab_account_pass(self):
        with patch.object(pub.subprocess,'run',side_effect=[SimpleNamespace(returncode=0,stdout=b'icnclab'),SimpleNamespace(returncode=0,stdout=b'true')]):pub.verify_github_access()

if __name__=='__main__':unittest.main()

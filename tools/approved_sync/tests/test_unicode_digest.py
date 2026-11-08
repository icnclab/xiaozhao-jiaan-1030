import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from sync_verified import source_digest
import test_toolkit as fixtures

class UnicodePathTest(unittest.TestCase):
    def test_chinese_document_changes_approval_digest(self):
        fixture=fixtures.ToolkitTests(methodName='test_secret_rule_blocks_export');fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        before=source_digest(fixture.repo,fixture.head)
        fixture.put('docs/uat/中文驗收.md','# synthetic test document\n')
        fixtures.command('git','-C',str(fixture.repo),'add','--','docs/uat/中文驗收.md')
        fixtures.command('git','-C',str(fixture.repo),'commit','-qm','unicode fixture')
        after=source_digest(fixture.repo,fixtures.command('git','-C',str(fixture.repo),'rev-parse','HEAD'))
        self.assertNotEqual(before,after)

if __name__=='__main__':unittest.main()

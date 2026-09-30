import sys
from pathlib import Path
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from ui_service import Application, UIError
from web_sources import SourcePolicy

class SuggestionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.app=Application(self.base,SourcePolicy({}))
        self.values={'url':'https://agency.example/news','publisher':'Example Agency','reason':'Official flight records'}
    def approve(self,row,**overrides):
        values={'id':row['id'],'decision':'approve','confirmed':True,'reviewer':'Local reviewer','type':'company','tier':2,'official':True}
        values.update(overrides)
        return self.app.decide_source(values)
    def test_pending_does_not_approve_and_confirmation_is_required(self):
        row=self.app.suggest_source(self.values)
        self.assertFalse(self.app.policy.qualify(self.values['url'])['allowed'])
        with self.assertRaises(UIError):self.approve(row,confirmed=False)
        self.assertEqual(self.app.source_suggestions()[0]['status'],'pending')
    def test_approval_persists_exact_host_and_classification(self):
        row=self.app.suggest_source(self.values);self.approve(row)
        reopened=Application(self.base,SourcePolicy({}))
        rule=reopened.policy.qualify(self.values['url'])
        self.assertTrue(rule['allowed']);self.assertEqual(rule['type'],'company')
        self.assertFalse(reopened.policy.qualify('https://other.agency.example/')['allowed'])
        self.assertEqual(reopened.history(),[])
        with self.assertRaises(UIError):self.approve(row)
    def test_reject_and_duplicate_suggestions(self):
        row=self.app.suggest_source(self.values)
        with self.assertRaises(UIError):self.app.suggest_source(self.values)
        self.app.decide_source({'id':row['id'],'decision':'reject'})
        self.assertFalse(Application(self.base,SourcePolicy({})).policy.qualify(self.values['url'])['allowed'])
    def test_invalid_urls_and_metadata_do_not_create_entries(self):
        for url in ['http://agency.example/','https://localhost/','https://127.0.0.1/','https://user:password@agency.example/','https://server.internal/']:
            with self.subTest(url=url),self.assertRaises(UIError):self.app.suggest_source(dict(self.values,url=url))
        row=self.app.suggest_source(self.values)
        for changes in [{'reviewer':''},{'tier':True},{'type':'invented'}]:
            with self.assertRaises(UIError):self.approve(row,**changes)
    def test_no_overwrite_or_policy_mutation_during_research(self):
        row=self.app.suggest_source(self.values);self.app.busy=True
        with self.assertRaises(UIError):self.approve(row)
        self.app.busy=False;self.app.policy.rules['agency.example']={'allowed':False}
        with self.assertRaises(UIError):self.approve(row)

if __name__=='__main__':unittest.main()

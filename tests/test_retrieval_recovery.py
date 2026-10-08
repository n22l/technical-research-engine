"""Regressions from production failure mechanisms, using synthetic content."""
import gzip
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from local_search import LocalSearchProvider, discovery_links
from web_sources import SourcePolicy


class RecoveryTests(unittest.TestCase):
    def test_blocked_legacy_pages_do_not_recrawl_on_every_question(self):
        from web_sources import FetchError
        policy=SourcePolicy({'agency.example':{'allowed':True,'publisher':'Agency','type':'government'}})
        with tempfile.TemporaryDirectory() as tmp,patch('local_search.Fetcher.fetch',side_effect=FetchError(403)) as fetch,patch('local_search.time.sleep'):
            p=LocalSearchProvider(Path(tmp),policy)
            p.entries=[{'url':'https://agency.example/','title':'Legacy','text':'Legacy text','epoch':0,'retrieved_at':'2026-01-01'}]
            p._crawl()
            q=LocalSearchProvider(Path(tmp),policy)
            self.assertTrue(q._load())
            calls=fetch.call_count
            self.assertEqual(q.search('reusable rocket'),[])
            self.assertEqual(fetch.call_count,calls)
            self.assertTrue(q.frontier)

    def test_declared_chinese_encoding_preserves_exact_citations(self):
        from web_sources import parse_document,decode_html
        policy=SourcePolicy({'agency.example':{'allowed':True,'publisher':'Agency','type':'government'}})
        text='中国可复用火箭进行了飞行试验。'
        body=('<meta charset="gb2312"><p>'+text+'</p>').encode('gb18030')
        doc=parse_document('https://agency.example/a',body,'text/html',policy)
        self.assertEqual(doc.passages[0]['passage'],text)
        loc=doc.passages[0]['location']
        self.assertEqual(doc.text[loc.character_start:loc.character_end],text)
        with self.assertRaises(UnicodeDecodeError):decode_html(b'<meta charset="utf-8"><p>\xff</p>')
        with self.assertRaises(ValueError):decode_html(b'<meta charset="unknown"><p>Text</p>')

    def test_cold_and_legacy_index_reach_citation_validated_review(self):
        from verify import research
        from verification_models import ResearchRequest
        import time
        good='https://agency.example/article'
        bad='https://agency.example/wrong-company'
        policy=SourcePolicy({'agency.example':{'allowed':True,'publisher':'Agency','type':'government',
            'tier':1,'crawl_seeds':[bad,good]}})
        def fetch(url):
            if url.endswith('robots.txt'):return b'User-agent: *\nDisallow:', 'text/plain'
            title='SpaceX' if url==good else 'Stoke Space'
            return f'<title>{title} test</title><main><p>The reusable rocket completed a flight test.</p></main>'.encode(),'text/html'
        for legacy in (False,True):
            with self.subTest(legacy=legacy),tempfile.TemporaryDirectory() as tmp,patch('local_search.Fetcher.fetch',side_effect=fetch),patch('local_search.time.sleep'),patch('verify.time.sleep'):
                base=Path(tmp);p=LocalSearchProvider(base,policy)
                if legacy:
                    p.entries=[{'url':good,'title':'SpaceX','text':'old page text','epoch':time.time(),'retrieved_at':'2026-01-01'}]
                    p.audit['indexed_at']='2026-01-01';p._save();p=LocalSearchProvider(base,policy)
                for query in ['SpaceX reusable rocket','SpaceX可复用火箭']:
                    result=research(ResearchRequest(query),policy,[],base,search_provider=p,review_only=True)
                    self.assertTrue(result['key_evidence'])
                    self.assertNotIn('CITATION_VALIDATION_FAILED',result['failures'])
                    self.assertTrue(all(e['exact_passage']=='The reusable rocket completed a flight test.' for e in result['key_evidence']))
                    self.assertEqual(result['search']['selected_urls'],[good])
                    self.assertIsNone(result['verdict'])

    def test_explicit_seed_survives_full_inventory_and_reports_empty_html(self):
        from search_discovery import SearchError
        policy=SourcePolicy({'agency.example':{'allowed':True,'publisher':'Agency','type':'government',
            'crawl_seeds':['https://agency.example/article']}})
        def fetch(url):
            if url.endswith('robots.txt'):return b'User-agent: *\nDisallow:', 'text/plain'
            return b'<html><script src="app.js"></script><app-root></app-root></html>','text/html'
        with tempfile.TemporaryDirectory() as tmp,patch('local_search.Fetcher.fetch',side_effect=fetch),patch('local_search.time.sleep'):
            p=LocalSearchProvider(Path(tmp),policy,max_urls_discovered=100)
            p.inventory={f'https://agency.example/old{i}':{'kind':'page','status':'PENDING'} for i in range(100)}
            with self.assertRaises(SearchError):p._crawl()
            self.assertEqual(p.inventory['https://agency.example/article']['failure_reason'],'SCRIPT_ONLY_OR_EMPTY_HTML')
            self.assertEqual(p.audit['site_coverage'][0]['failure_reasons'],{'SCRIPT_ONLY_OR_EMPTY_HTML':1})

    def test_entities_missions_and_context_without_capability_leakage(self):
        from retrieval_constraints import subject_matches,coverage
        from passage_ranking import rank_passages
        self.assertFalse(subject_matches('SpaceX reuse both stages','Stoke Space reusable rocket stages'))
        self.assertFalse(subject_matches('Crew-13 launch','Crew-12 launch','Crew-13 launch'))
        self.assertTrue(subject_matches('Crew 13 launch','The launch was successful.','Crew-13'))
        self.assertFalse(subject_matches('SpaceX reusable rocket','A rocket flew.','SpaceX reusable rocket'))
        self.assertTrue(subject_matches('SpaceX reusable rocket','The reusable rocket flew.','SpaceX test'))
        self.assertFalse(subject_matches('SpaceX reusable rocket','Stoke Space reusable rocket flew.','SpaceX test'))
        self.assertEqual(coverage('Crew-13 launch',['Crew-12 launch'])['missing_subjects'],['crew-13'])
        rows=[{'passage_id':'right:p1','passage':'The reusable rocket flew.','source':{'id':'right','title':'SpaceX test'}},
              {'passage_id':'wrong:p1','passage':'Stoke Space reusable rocket flew.','source':{'id':'wrong','title':'SpaceX comparison'}}]
        for query in ['SpaceX reusable rocket','SpaceX可复用火箭']:
            self.assertEqual([h['passage_id'] for h in rank_passages(rows,query)],['right:p1'])

    def test_failed_maps_cannot_starve_articles_and_back_off(self):
        clock, calls = [0], []
        def fetch(url):
            calls.append(url)
            if url.endswith('robots.txt'): return b'User-agent: *\nDisallow:', 'text/plain'
            if url.endswith('.xml'):
                clock[0] += 10
                raise ValueError('synthetic timeout')
            return b'<p>Relevant reusable booster reflight.</p>', 'text/html'
        policy = SourcePolicy({'agency.example': {'allowed':True,'publisher':'Agency','type':'government',
            'sitemaps':['https://agency.example/map'+str(i)+'.xml' for i in range(20)]}})
        with tempfile.TemporaryDirectory() as tmp, patch('local_search.Fetcher.fetch',side_effect=fetch), patch('local_search.time.sleep'), patch('local_search.time.monotonic',side_effect=lambda:clock[0]):
            p=LocalSearchProvider(Path(tmp),policy)
            p._crawl()
            self.assertEqual(len(p.entries),1)
            page_index=calls.index('https://agency.example/')
            self.assertLessEqual(sum(u.endswith('.xml') for u in calls[:page_index]),2)
            failed=[u for u,s in p.inventory.items() if s['status']=='FETCH_FAILED']
            self.assertTrue(failed)
            self.assertTrue(all(p.inventory[u]['retry_after']>0 for u in failed))
            calls.clear();clock[0]=0;p._crawl()
            self.assertFalse(set(failed)&set(calls))

    def test_gzip_maps_bounded_and_entities_rejected(self):
        url='https://agency.example/map.xml.gz'
        body=b'<urlset><url><loc>https://agency.example/article</loc></url></urlset>'
        self.assertEqual(discovery_links(gzip.compress(body),url),[('https://agency.example/article','page')])
        for raw in [b'x'*2_000_001,b'<!DOCTYPE x><urlset/>']:
            with self.assertRaises(ValueError): discovery_links(gzip.compress(raw),url)

    def test_fresh_snapshot_cannot_hide_unmigrated_pages(self):
        import json,time
        policy=SourcePolicy({'agency.example':{'allowed':True,'publisher':'Agency','type':'government'}})
        with tempfile.TemporaryDirectory() as tmp:
            p=LocalSearchProvider(Path(tmp),policy)
            p.entries=[{'url':'https://agency.example/old','title':'SpaceX reuse both stages',
                'text':'SpaceX reuse both stages','retrieved_at':'2026-01-01','epoch':time.time()}]
            p.audit['indexed_at']='2026-01-01';p._save()
            q=LocalSearchProvider(Path(tmp),policy)
            self.assertFalse(q._load())
            self.assertEqual(q.search('SpaceX reuse both stages'),[])
            self.assertEqual(q.audit['legacy_pages'],1)
            def fetch(url):
                return (b'User-agent: *\nDisallow:', 'text/plain') if url.endswith('robots.txt') else (b'<p>SpaceX reuse both stages is a synthetic query.</p>','text/html')
            with patch('local_search.Fetcher.fetch',side_effect=fetch),patch('local_search.time.sleep'):
                q._crawl()
            self.assertEqual(q.audit['legacy_pages'],0)
            self.assertTrue(q.search('SpaceX reuse both stages')[0].local_match)


if __name__=='__main__':unittest.main()

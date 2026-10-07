import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from passage_ranking import rank_passages, sentences, match_details
from web_sources import SourcePolicy, parse_document
from local_search import LocalSearchProvider
from evaluate_passages import evaluate


class PassageUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.policy = SourcePolicy({'agency.example': {'allowed': True, 'type': 'government', 'publisher': 'Agency',
                                    'crawl_hosts': ['science.agency.example']}})

    def test_explicit_scope_and_lookalikes(self):
        for host, allowed in [('agency.example', True), ('science.agency.example', True),
                              ('data.agency.example', False), ('evil-agency.example', False)]:
            self.assertEqual(self.policy.qualify('https://'+host+'/article')['allowed'], allowed)
        restricted = SourcePolicy({'agency.example': {'allowed':True, 'publisher':'A', 'allowed_path_prefixes':['/science/'], 'excluded_path_prefixes':['/science/private/']}})
        self.assertFalse(restricted.qualify('https://agency.example/science/private/x')['allowed'])
        self.assertTrue(restricted.qualify('https://agency.example/robots.txt')['allowed'])
        self.assertFalse(restricted.qualify('https://agency.example/science/%2e%2e/private/x')['allowed'])

    def test_exact_sentences_and_abbreviations(self):
        text = 'Dr. Smith measured 2.5 seconds. A booster flew! 中国完成试验。再次测试；'
        ss = sentences(text, 'doc:p1')
        self.assertEqual(len(ss), 4)
        for s in ss: self.assertEqual(text[s['character_start']:s['character_end']], s['text'])

    def test_compact_paragraph_beats_scattered_title(self):
        rows = [{'passage_id': 'a:p1', 'source': {'id':'a', 'title':'reusable booster reflight'},
                 'passage': 'reusable ' + 'unrelated words '*100 + 'booster ' + 'unrelated '*100 + 'reflight.'},
                {'passage_id':'b:p1', 'source':{'id':'b'}, 'passage':'The reusable booster completed reflight.'}]
        hits = rank_passages(rows, 'reusable booster reflight')
        self.assertEqual(hits[0]['passage_id'], 'b:p1')
        self.assertLess(hits[0]['retrieval_match']['minimum_term_window'], hits[1]['retrieval_match']['minimum_term_window'])

    def test_main_boilerplate_and_locations(self):
        doc = parse_document('https://agency.example/a', b'<nav><p>booster reflight menu</p></nav><p>Other</p><main><h2>Flight</h2><p>The booster flew. It landed.</p></main>', 'text/html', self.policy)
        self.assertEqual(len(doc.passages), 1)
        p = doc.passages[0]
        self.assertEqual(doc.text[p['location'].character_start:p['location'].character_end], p['passage'])
        self.assertEqual(p['location'].section_heading, 'Flight')

    def test_nested_maps_subdomain_robots_and_reindex(self):
        def fetch(url):
            if url.endswith('/robots.txt'):
                return b'User-agent: *\nDisallow: /private\nSitemap: https://agency.example/root.xml', 'text/plain'
            if url.endswith('root.xml'):
                return b'<sitemapindex><sitemap><loc>https://agency.example/child.xml</loc></sitemap></sitemapindex>', 'application/xml'
            if url.endswith('child.xml'):
                return b'<urlset><url><loc>https://science.agency.example/a/b/c/d/article</loc></url><url><loc>https://agency.example/private</loc></url></urlset>', 'application/xml'
            return ('<p>Unique booster reflight ' + url + '</p>').encode(), 'text/html'
        with tempfile.TemporaryDirectory() as tmp, patch('local_search.time.sleep'), patch('local_search.Fetcher.fetch', side_effect=fetch) as f:
            provider = LocalSearchProvider(Path(tmp), self.policy, max_pages=20, max_depth=0)
            hits = provider.search('booster reflight')
            self.assertTrue(any('/a/b/c/d/article' in h.url for h in hits))
            self.assertIn('https://science.agency.example/robots.txt', [c.args[0] for c in f.call_args_list])
            self.assertNotIn('https://agency.example/private', [c.args[0] for c in f.call_args_list])
            self.assertTrue(all(h.local_match['best_sentence'] for h in hits))
            self.assertEqual(provider.audit['site_coverage'][0]['status'], 'ROBOTS_LIMITED')
            f.reset_mock(); result = provider.reindex(); f.assert_not_called()
            self.assertGreater(result['reindexed'], 0)

    def test_traps_meaningful_query_and_tracking(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = LocalSearchProvider(Path(tmp), self.policy)
            for suffix in ['/calendar/2026/1', '/a?page=2', '/a?sort=new', '/login']:
                with self.assertRaises(ValueError): p._allowed('https://agency.example'+suffix)
            self.assertIn('id=123', p._allowed('https://agency.example/a?id=123&utm_source=test#top'))
            self.assertNotIn('utm_source', p._allowed('https://agency.example/a?id=123&utm_source=test#top'))

    def test_metrics(self):
        report = evaluate()
        self.assertEqual(report['after']['document_hit_at_5'], 1)
        self.assertEqual(report['after']['passage_hit_at_5'], 1)
        self.assertEqual(report['after']['passage_mrr'], 1)

    def test_more_than_five_maps_resumable(self):
        policy = SourcePolicy({'agency.example': {'allowed':True, 'publisher':'Agency', 'type':'government',
            'sitemaps':['https://agency.example/root.xml']}})
        def fetch(url):
            if url.endswith('robots.txt'): return b'User-agent: *\nDisallow:', 'text/plain'
            if url.endswith('root.xml'):
                return ('<sitemapindex>'+''.join(f'<sitemap><loc>https://agency.example/m{i}.xml</loc></sitemap>' for i in range(12))+'</sitemapindex>').encode(), 'application/xml'
            if url.endswith('.xml'):
                return ('<urlset><url><loc>'+url.replace('.xml','/deep/article')+'</loc></url></urlset>').encode(), 'application/xml'
            return ('<p>Booster reflight '+url+'</p>').encode(), 'text/html'
        with tempfile.TemporaryDirectory() as tmp, patch('local_search.time.sleep'), patch('local_search.Fetcher.fetch', side_effect=fetch):
            first = LocalSearchProvider(Path(tmp), policy, max_pages=30, max_sitemap_files=6)
            first.search('booster reflight')
            self.assertTrue(first.frontier)
            self.assertEqual(first.audit['site_coverage'][0]['status'],'BUDGET_LIMITED')
            second = LocalSearchProvider(Path(tmp), policy, max_pages=30, max_sitemap_files=20, refresh=True)
            second.search('booster reflight')
            self.assertEqual(len(second.maps_read),13)
            self.assertEqual(second.audit['site_coverage'][0]['status'],'COMPLETE_WITHIN_DISCOVERED_SCOPE')

    def test_not_modified_reuses_capture_and_passages(self):
        policy = SourcePolicy({'agency.example': {'allowed':True, 'publisher':'Agency', 'type':'government'}})
        def initial(url):
            return (b'User-agent: *\nDisallow:', 'text/plain') if url.endswith('robots.txt') else (b'<p>Booster reflight.</p>', 'text/html')
        with tempfile.TemporaryDirectory() as tmp, patch('local_search.time.sleep'):
            with patch('local_search.Fetcher.fetch',side_effect=initial):
                p = LocalSearchProvider(Path(tmp),policy); p.search('booster reflight')
            before = p.entries[0]['passages']
            def unchanged(url):
                return (b'User-agent: *\nDisallow:', 'text/plain') if url.endswith('robots.txt') else (None,None)
            with patch('local_search.Fetcher.fetch',side_effect=unchanged):
                p.refresh=True; p._crawl()
            self.assertEqual(before,p.entries[0]['passages'])
            self.assertEqual(len(list(Path(tmp).glob('crawl-capture-*'))),1)

    def test_publisher_refresh_preserves_other_frontier(self):
        policy = SourcePolicy({'a.example': {'allowed':True,'publisher':'A','type':'government'},
                               'b.example': {'allowed':True,'publisher':'B','type':'government'}})
        def fetch(url):
            return (b'User-agent: *\nDisallow:', 'text/plain') if url.endswith('robots.txt') else (b'<p>Booster reflight.</p>', 'text/html')
        with tempfile.TemporaryDirectory() as tmp, patch('local_search.time.sleep'), patch('local_search.Fetcher.fetch',side_effect=fetch) as calls:
            p=LocalSearchProvider(Path(tmp),policy,publisher_filter='a.example')
            p.frontier=[('https://b.example/pending',0,'page')]
            p._crawl()
            self.assertIn(('https://b.example/pending',0,'page'),p.frontier)
            self.assertFalse(any('b.example' in c.args[0] for c in calls.call_args_list))

    def test_sentence_tampering_rejected(self):
        from verification import candidates, decompose, validate_citation
        from verification_models import ResearchRequest
        doc=parse_document('https://agency.example/a',b'<p>Booster reflight happened.</p>','text/html',self.policy)
        e=candidates(decompose(ResearchRequest('booster reflight')),[doc])[0]
        self.assertTrue(validate_citation(e,[doc],{'c1'}))
        e.retrieval_match['best_sentence']['text']='Invented sentence.'
        self.assertFalse(validate_citation(e,[doc],{'c1'}))


if __name__ == '__main__': unittest.main()

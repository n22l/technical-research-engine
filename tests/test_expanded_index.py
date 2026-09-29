"""Synthetic broad-index, incremental and ranking regressions."""
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from local_search import LocalSearchProvider, discovery_links, IndexText
from web_sources import SourcePolicy


class ExpandedIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.policy = SourcePolicy({'agency.example': {'allowed': True, 'tier': 1, 'type': 'government', 'publisher': 'Agency'}})

    def fetch(self, url):
        if url.endswith('robots.txt'):
            return b'User-agent: *\nDisallow: /private\nSitemap: https://agency.example/map.xml', 'text/plain'
        if url.endswith('map.xml'):
            return b'<urlset><url><loc>https://agency.example/flight</loc></url><url><loc>https://evil.example/x</loc></url><url><loc>https://agency.example/private</loc></url></urlset>', 'application/xml'
        return b'<title>Booster record</title><nav>unrelated navigation</nav><p>Booster reflight occurred.</p>', 'text/html'

    def test_sitemap_discovery_resumes_without_losing_existing_entries(self):
        with patch('local_search.time.sleep'), patch('local_search.Fetcher.fetch', side_effect=self.fetch) as fetch:
            first = LocalSearchProvider(self.base, self.policy, max_pages=10, per_host=2)
            first.search('booster')
            self.assertEqual(len(first.entries), 1)
            self.assertGreater(first.audit['pending_urls'], 0)
            second = LocalSearchProvider(self.base, self.policy, max_pages=10, per_host=2, refresh=True)
            second.search('booster')
            self.assertEqual(len(second.entries), 2)
            self.assertIn('https://agency.example/flight', [e['url'] for e in second.entries])
            urls = [c.args[0] for c in fetch.call_args_list]
            self.assertNotIn('https://evil.example/x', urls)
            self.assertNotIn('https://agency.example/private', urls)
            self.assertNotIn('unrelated navigation', second.entries[0]['text'])

    def test_rss_atom_and_entity_rejection(self):
        self.assertEqual(discovery_links(b'<rss><channel><item><link>/flight</link></item></channel></rss>', 'https://agency.example/feed'), [('https://agency.example/flight', 'page')])
        self.assertEqual(discovery_links(b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><link href="/flight"/></entry></feed>', 'https://agency.example/feed'), [('https://agency.example/flight', 'page')])
        for body in [b'<!DOCTYPE x [<!ENTITY x "boom">]><rss>&x;</rss>', '<!DOCTYPE x><rss/>'.encode('utf-16')]:
            with self.assertRaises((ValueError, UnicodeError)):
                discovery_links(body, 'https://agency.example/')

    def test_time_budget_saves_pending_work(self):
        with patch('local_search.time.sleep'), patch('local_search.Fetcher.fetch', side_effect=self.fetch), patch('local_search.time.monotonic', side_effect=[0, 0, 121]):
            provider = LocalSearchProvider(self.base, self.policy)
            provider.search('booster')
            self.assertEqual(provider.audit['page_attempts'], 1)
            self.assertTrue(provider.audit['budget_exhausted'])
            self.assertTrue(provider.frontier)

    def test_failed_refresh_retains_prior_discovery(self):
        with patch('local_search.time.sleep'), patch('local_search.Fetcher.fetch', side_effect=self.fetch):
            LocalSearchProvider(self.base, self.policy, max_pages=1).search('booster')
        with patch('local_search.time.sleep'), patch('local_search.Fetcher.fetch', side_effect=ValueError('offline')):
            provider = LocalSearchProvider(self.base, self.policy, max_pages=1, refresh=True)
            self.assertTrue(provider.search('booster'))
            self.assertTrue(provider.audit['cache_used'])
            self.assertTrue(provider.audit['events'])

    def test_rare_title_terms_and_phrases_beat_generic_repetition(self):
        provider = LocalSearchProvider(self.base, self.policy)
        provider.entries = [
            {'url':'https://agency.example/generic','title':'News','text':'booster ' * 100,'retrieved_at':'2026-01-01'},
            {'url':'https://agency.example/flight','title':'Falcon 9 reflight 2025','text':'Flight record.','retrieved_at':'2026-01-01'}]
        self.assertEqual(provider.search('Falcon 9 reflight 2025')[0].url, 'https://agency.example/flight')
        self.assertEqual(provider.search('the and of'), [])

    def test_bounds_and_cleaner(self):
        for kwargs in [{'max_pages':501}, {'per_host':101}, {'max_depth':4}, {'max_seconds':601}]:
            with self.assertRaises(ValueError):
                LocalSearchProvider(self.base, self.policy, **kwargs)
        cleaner = IndexText()
        cleaner.feed('<nav>menu<script>bad()</script></nav><article>useful</article><footer>links</footer>')
        self.assertEqual(''.join(cleaner.parts), 'useful')


if __name__ == '__main__':
    unittest.main()

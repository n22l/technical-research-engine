import sys, unittest, tempfile, json, os
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from local_search import LocalSearchProvider
from web_sources import SourcePolicy
from search_discovery import SearchError, configured_provider

class LocalTests(unittest.TestCase):
    def setUp(self):
        self.policy = SourcePolicy({'agency.example': {'allowed': True, 'tier': 1, 'type': 'government', 'publisher': 'Agency'}})
    def fetch(self, url):
        if url.endswith('/robots.txt'):
            return b'User-agent: *\nDisallow: /private\n', 'text/plain'
        return b'<title>Booster record</title><p>Booster reflight record.</p><a href="/next">Next</a><a href="/private">Private</a><a href="https://evil.example/">Bad</a>', 'text/html'
    def test_bounded_crawl_and_private_cache(self):
        with tempfile.TemporaryDirectory() as tmp, patch('local_search.time.sleep'), patch('local_search.Fetcher.fetch', side_effect=self.fetch) as fetch:
            provider = LocalSearchProvider(Path(tmp), self.policy, max_pages=3)
            results = provider.search('booster', limit=5)
            self.assertEqual(len(results), 1)  # Identical paragraphs do not dominate results.
            self.assertTrue(all(r.snippet == '' for r in results))
            self.assertNotIn('https://agency.example/private', [c.args[0] for c in fetch.call_args_list])
            self.assertNotIn('https://evil.example/', [c.args[0] for c in fetch.call_args_list])
            self.assertEqual(len(list(Path(tmp).glob('local-index-*.json'))), 1)
            fetch.reset_mock()
            cached = LocalSearchProvider(Path(tmp), self.policy, max_pages=3)
            self.assertTrue(cached.search('booster', limit=1))
            fetch.assert_not_called()
            self.assertTrue(cached.audit['cache_used'])
    def test_robots_failure_is_not_no_evidence(self):
        with tempfile.TemporaryDirectory() as tmp, patch('local_search.time.sleep'), patch('local_search.Fetcher.fetch', side_effect=ValueError('unavailable')) as fetch:
            with self.assertRaises(SearchError):
                LocalSearchProvider(Path(tmp), self.policy).search('booster')
            self.assertEqual(fetch.call_count, 1)
    def test_refresh_and_policy_change_invalidate_cache(self):
        with tempfile.TemporaryDirectory() as tmp, patch('local_search.time.sleep'), patch('local_search.Fetcher.fetch', side_effect=self.fetch) as fetch:
            LocalSearchProvider(Path(tmp), self.policy, max_pages=1).search('booster')
            fetch.reset_mock()
            LocalSearchProvider(Path(tmp), self.policy, max_pages=1, refresh=True).search('booster')
            self.assertTrue(fetch.called)
            self.policy.rules['agency.example']['allowed'] = False
            with self.assertRaises(SearchError):
                LocalSearchProvider(Path(tmp), self.policy, max_pages=1).search('booster')
    def test_default_provider_has_no_api_key_requirement(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {}, clear=True):
            provider = configured_provider(base=Path(tmp), policy=self.policy)
            self.assertEqual(provider.name, 'local')

    def test_html_robots_error_page_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp, patch('local_search.time.sleep'), patch('local_search.Fetcher.fetch', return_value=(b'<html>Error</html>', 'text/html')) as fetch:
            with self.assertRaises(SearchError):
                LocalSearchProvider(Path(tmp), self.policy).search('booster')
            self.assertEqual(fetch.call_count, 1)

    def test_question_only_cli_uses_local_and_keeps_passages_private(self):
        import contextlib
        import io
        from verify import main
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'policy.json').write_text(json.dumps({'sources': self.policy.rules}))
            out = io.StringIO()
            with patch.dict('os.environ', {'TECH_RESEARCH_DATA_DIR': tmp}), \
                 patch('local_search.time.sleep'), patch('verify.time.sleep'), \
                 patch('web_sources.Fetcher.fetch', side_effect=self.fetch), contextlib.redirect_stdout(out):
                os.environ.pop('TECH_RESEARCH_SEARCH_PROVIDER', None)
                self.assertEqual(main(['research', 'booster reflight', '--policy', 'policy.json', '--max-crawl-pages', '2']), 0)
            report = json.loads(next(base.glob('result-*.json')).read_text(encoding='utf-8'))
            self.assertEqual(report['search']['provider'], 'local')
            self.assertTrue(report['search']['local_index']['indexed_pages'])
            self.assertTrue(report['key_evidence'])
            self.assertIsNone(report['verdict'])
            self.assertNotIn('Booster reflight record.', out.getvalue())

if __name__ == '__main__': unittest.main()

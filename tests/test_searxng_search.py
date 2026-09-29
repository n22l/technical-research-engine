"""SearXNG contract tests use synthetic responses; no public instance probing."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from urllib.parse import urlsplit, parse_qs
from searxng_search import SearXNGProvider
from search_discovery import SearchError, configured_provider
from web_sources import FetchError, SourcePolicy
from verification_models import ResearchRequest
from verify import research


class SearXNGTests(unittest.TestCase):
    def provider(self):
        return SearXNGProvider('https://search.example/instance/')

    def test_request_and_bounded_structured_results(self):
        provider = self.provider()
        payload = {'results': [{'title': 'Record', 'url': 'https://agency.example/a',
                                'content': 'Discovery only'}] * 3}
        with patch.object(provider.fetcher, 'fetch', return_value=(json.dumps(payload).encode(), 'application/json')) as fetch:
            results = provider.search('booster & reflight?', limit=2)
        request = urlsplit(fetch.call_args.args[0])
        self.assertEqual(request.path, '/instance/search')
        self.assertEqual(parse_qs(request.query)['q'], ['booster & reflight?'])
        self.assertEqual(parse_qs(request.query)['format'], ['json'])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].provider, 'searxng')
        self.assertEqual(provider.fetcher.accept, 'application/json')

    def test_configuration_rejects_unsafe_destinations(self):
        for url in ['', 'http://search.example/', 'https://localhost/', 'https://127.0.0.1/',
                    'https://10.0.0.1/', 'https://169.254.169.254/', 'https://[::1]/',
                    'https://user:secret@search.example/', 'https://search.example/?key=secret',
                    'https://search.example/#fragment', 'https://search.example:8080/']:
            with self.subTest(url=url), self.assertRaisesRegex(SearchError, '^SEARCH_UNAVAILABLE$'):
                SearXNGProvider(url)
        with patch.dict('os.environ', {'TECH_RESEARCH_SEARXNG_URL': 'https://search.example'}):
            self.assertEqual(configured_provider('searxng').name, 'searxng')

    def test_private_dns_rejected_before_connection(self):
        with patch('web_sources.socket.getaddrinfo', return_value=[(0, 0, 0, '', ('127.0.0.1', 443))]), \
             patch('web_sources.PinnedHTTPS') as connection:
            with self.assertRaisesRegex(SearchError, '^SEARCH_PROVIDER_ERROR$'):
                self.provider().search('test')
        connection.assert_not_called()

    def test_http_failures_are_sanitized_without_retry(self):
        for status, code in [(401, 'SEARCH_AUTH_FAILED'), (403, 'SEARCH_AUTH_FAILED'),
                             (429, 'SEARCH_RATE_LIMITED'), (302, 'SEARCH_PROVIDER_ERROR'),
                             (500, 'SEARCH_PROVIDER_ERROR')]:
            provider = self.provider()
            with patch.object(provider.fetcher, 'fetch', side_effect=FetchError(status)) as fetch:
                with self.assertRaisesRegex(SearchError, '^' + code + '$'):
                    provider.search('test')
                self.assertEqual(fetch.call_count, 1)

    def test_redirect_and_oversize_use_existing_transport_guards(self):
        for status, length in [(302, '0'), (200, '2000001')]:
            conn = MagicMock()
            response = conn.getresponse.return_value
            response.status = status
            response.getheader.side_effect = lambda name, default=None: length if name == 'Content-Length' else default
            with patch('web_sources.socket.getaddrinfo', return_value=[(0, 0, 0, '', ('8.8.8.8', 443))]), \
                 patch('web_sources.PinnedHTTPS', return_value=conn):
                with self.assertRaises(SearchError):
                    self.provider().search('test')
            response.read.assert_not_called()
            conn.close.assert_called_once()

    def test_malformed_and_partial_engine_failures_are_not_no_results(self):
        for payload in [[], {}, {'results': 'bad'}, {'results': [None]},
                        {'results': [{'url': 7}]}, {'results': [], 'unresponsive_engines': [['engine', 'timeout']]},
                        {'results': [], 'unresponsive_engines': 'bad'}]:
            provider = self.provider()
            with patch.object(provider.fetcher, 'fetch', return_value=(json.dumps(payload).encode(), 'application/json')):
                with self.assertRaisesRegex(SearchError, '^SEARCH_PROVIDER_ERROR$'):
                    provider.search('test')
        provider = self.provider()
        with patch.object(provider.fetcher, 'fetch', return_value=(b'<html>error</html>', 'text/html')):
            with self.assertRaises(SearchError):
                provider.search('test')

    def test_no_results_and_query_bounds(self):
        provider = self.provider()
        with patch.object(provider.fetcher, 'fetch', return_value=(b'{"results":[]}', 'application/json')) as fetch:
            self.assertEqual(provider.search('test'), [])
            for query, limit in [('', 5), ('x' * 601, 5), ('test', 21), ('test', 0)]:
                with self.assertRaises(SearchError):
                    provider.search(query, limit=limit)
            self.assertEqual(fetch.call_count, 1)

    def test_end_to_end_snippet_isolation_and_source_policy(self):
        provider = self.provider()
        payload = {'results': [
            {'url': 'https://agency.example/a', 'content': 'SNIPPET_SENTINEL booster success'},
            {'url': 'https://blog.example/b', 'content': 'SNIPPET_SENTINEL unsupported'}]}
        policy = SourcePolicy({'agency.example': {'allowed': True, 'tier': 1, 'type': 'government', 'publisher': 'Agency'}})
        with tempfile.TemporaryDirectory() as tmp, patch.object(provider.fetcher, 'fetch', return_value=(json.dumps(payload).encode(), 'application/json')), \
             patch('searxng_search.time.sleep'), patch('verify.time.sleep'), \
             patch('verify.Fetcher.fetch', return_value=(b'<p>Booster inspection record.</p>', 'text/html')) as fetch:
            result = research(ResearchRequest('booster'), policy, [], Path(tmp), search_provider=provider, review_only=True)
        self.assertEqual(result['search']['selected_urls'], ['https://agency.example/a'])
        self.assertEqual(fetch.call_count, 1)
        self.assertTrue(result['key_evidence'])
        self.assertNotIn('SNIPPET_SENTINEL', json.dumps(result['key_evidence']))
        self.assertIsNone(result['verdict'])
        self.assertNotIn('search.example', policy.rules)


if __name__ == '__main__':
    unittest.main()

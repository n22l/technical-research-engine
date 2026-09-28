"""Synthetic API and fetched-page fixtures; never production search claims."""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from search_discovery import (BraveSearchProvider, SearchResult, SearchError, discover,
                              normalize_url, configured_provider, evaluate_discovery)
from verification_models import ResearchRequest
from verification import decompose
from web_sources import SourcePolicy
from verify import research, main


class FakeProvider:
    name = 'fixture'
    def __init__(self, urls=(), error=None):
        self.urls, self.error, self.calls = urls, error, []

    def search(self, query, *, limit):
        self.calls.append((query, limit))
        if self.error:
            raise SearchError(self.error)
        return [SearchResult('Discovery only', url, 'SNIPPET_SENTINEL booster proven TRUE',
                             self.name, i, '2026-01-01T00:00:00+00:00')
                for i, url in enumerate(self.urls[:limit], 1)]


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.policy = SourcePolicy({
            'agency.example': {'allowed': True, 'tier': 1, 'type': 'government', 'primary': True, 'publisher': 'Agency'},
            'news.example': {'allowed': True, 'tier': 2, 'type': 'major_news', 'publisher': 'News'},
            'blog.example': {'allowed': False, 'type': 'discovery_only', 'publisher': 'Blog'},
        })
        self.request = ResearchRequest('Test booster reflight?', requested_as_of_date='2026-06-01', domain='aerospace')
        self.claims = decompose(self.request)

    def test_url_normalization_preserves_identity(self):
        self.assertEqual(normalize_url('https://AGENCY.example:443/a?id=1&utm_source=x&id=2#part'),
                         'https://agency.example/a?id=1&id=2')
        self.assertNotEqual(normalize_url('https://agency.example/a?id=1'),
                            normalize_url('https://agency.example/a?id=2'))
        for url in ['file:///tmp/a', 'http://agency.example', 'https://user:password@agency.example',
                    'https://127.0.0.1/a', 'https://169.254.169.254/', 'https://10.0.0.1/',
                    'https://[::1]/', 'https://localhost/', 'https://intranet/', 'https://a.internal/',
                    'https://a.local/', 'https://agency.example\\@evil.example']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                normalize_url(url)

    def test_policy_ranking_diversity_and_deduplication(self):
        provider = FakeProvider(['https://news.example/story', 'https://agency.example/a?utm_source=x',
                                 'https://agency.example/a', 'https://agency.example/b', 'https://unknown.gov/'])
        report = discover(self.claims, self.policy, [], provider, max_sources=2)
        self.assertEqual(report['selected_urls'], ['https://agency.example/a', 'https://news.example/story'])
        self.assertEqual(len(report['candidates']), 4)
        unknown = next(c for c in report['candidates'] if c['url'] == 'https://unknown.gov/')
        self.assertEqual(unknown['policy_note'], 'UNREGISTERED_SOURCE')
        self.assertEqual(report['status'], 'SEARCH_COMPLETE')
        self.assertTrue(any(d['original_url'].endswith('utm_source=x')
                            for c in report['candidates'] for d in c['discoveries']))

    def test_queries_are_bounded_and_cover_intents(self):
        provider = FakeProvider()
        claims = decompose(self.request, ['First booster claim', 'Second booster claim'])
        report = discover(claims, self.policy, [], provider, domain='aerospace', max_queries=8)
        self.assertEqual(len(provider.calls), 8)
        self.assertEqual({q['claim_id'] for q in report['queries_issued']}, {'c1', 'c2'})
        single = discover(self.claims, self.policy, [], FakeProvider(), domain='aerospace')
        self.assertEqual({q['intent'] for q in single['queries_issued']},
                         {'PRIMARY_SOURCE', 'OFFICIAL_RECORD', 'INDEPENDENT_CONFIRMATION',
                          'LATEST_UPDATE', 'CONTRADICTION_OR_CORRECTION'})
        self.assertTrue(all(len(q['query']) <= 600 for q in report['queries_issued']))

    def test_blogs_and_unsafe_urls_never_selected(self):
        report = discover(self.claims, self.policy, [], FakeProvider([
            'https://blog.example/a', 'https://unknown.edu/a', 'https://127.0.0.1/']))
        self.assertEqual(report['selected_urls'], [])
        self.assertEqual({c['source_policy_status'] for c in report['candidates']},
                         {'DISCOVERY_ONLY', 'UNKNOWN', 'REJECTED'})

    def test_search_error_stops_after_one_call_and_suppresses_verdict(self):
        for code in ['SEARCH_AUTH_FAILED', 'SEARCH_RATE_LIMITED', 'SEARCH_PROVIDER_ERROR']:
            provider = FakeProvider(error=code)
            with tempfile.TemporaryDirectory() as tmp:
                result = research(self.request, self.policy, [], Path(tmp), search_provider=provider)
            self.assertEqual(len(provider.calls), 1)
            self.assertIn(code, result['failures'])
            self.assertIsNone(result['verdict'])
            self.assertNotIn('INSUFFICIENT_EVIDENCE', result['failures'])

    def test_successful_empty_or_unapproved_search_is_insufficient(self):
        for urls in [[], ['https://blog.example/a']]:
            with tempfile.TemporaryDirectory() as tmp:
                result = research(self.request, self.policy, [], Path(tmp), search_provider=FakeProvider(urls))
            self.assertEqual(result['verdict'], 'INSUFFICIENT_PUBLIC_EVIDENCE')
            self.assertEqual(result['search']['status'], 'SEARCH_COMPLETE')

    def test_snippet_never_becomes_evidence_even_if_fetch_fails(self):
        provider = FakeProvider(['https://agency.example/a', 'https://news.example/b'])
        body = b'<meta name="date" content="2026-01-01"><h2>Result</h2><p>Test booster has not reflown.</p>'
        for failure in [False, True]:
            with tempfile.TemporaryDirectory() as tmp, patch('verify.time.sleep'), patch('verify.Fetcher.fetch') as fetch:
                fetch.side_effect = ValueError('fetch failed') if failure else None
                fetch.return_value = (body, 'text/html')
                result = research(self.request, self.policy, [], Path(tmp), search_provider=provider, review_only=True)
                self.assertEqual(fetch.call_count, 2)
                self.assertNotIn('SNIPPET_SENTINEL', json.dumps(result['key_evidence']))
                self.assertIsNone(result['verdict'])
                if not failure:
                    self.assertTrue(result['key_evidence'])
                    self.assertIn('not reflown', result['key_evidence'][0]['exact_passage'])
                    self.assertTrue(result['source_differences']['likely_dependencies'])
                    self.assertEqual(len(list(Path(tmp).glob('capture-*.bin'))), 2)
                else:
                    self.assertEqual(result['key_evidence'], [])

    def test_offline_does_not_call_search_or_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'fixture.html').write_text('<p>Test booster reflight record.</p>')
            provider = FakeProvider(error='SEARCH_AUTH_FAILED')
            with patch('verify.Fetcher.fetch', side_effect=AssertionError('network')):
                result = research(self.request, self.policy, ['https://agency.example/a'], base, offline=True,
                    captures={'https://agency.example/a': {'file': 'fixture.html', 'media_type': 'text/html'}},
                    search_provider=provider, review_only=True)
            self.assertEqual(provider.calls, [])
            self.assertTrue(result['key_evidence'])
            self.assertEqual(result['search']['status'], 'OFFLINE')

    def test_no_bundle_question_file_and_no_sensitive_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'question.txt').write_text('PRIVATE_QUESTION booster?', encoding='utf-8')
            (base / 'policy.json').write_text(json.dumps({'sources': self.policy.rules}))
            out = io.StringIO()
            with patch.dict(os.environ, {'TECH_RESEARCH_DATA_DIR': tmp, 'TECH_RESEARCH_SEARCH_PROVIDER': 'brave'}), \
                 patch('verify.configured_provider', return_value=FakeProvider(['https://agency.example/a'])), \
                 patch('verify.Fetcher.fetch', return_value=(b'<p>PRIVATE_PASSAGE booster.</p>', 'text/html')), \
                 patch('verify.time.sleep'), contextlib.redirect_stdout(out):
                self.assertEqual(main(['research', '--question-file', 'question.txt', '--policy', 'policy.json']), 0)
            self.assertNotIn('PRIVATE_', out.getvalue())
            result = json.loads(next(base.glob('result-*.json')).read_text(encoding='utf-8'))
            self.assertIsNone(result['verdict'])
            self.assertEqual(result['request']['text'], 'PRIVATE_QUESTION booster?')
            self.assertTrue(result['run_manifest']['search']['queries_issued'])

    def test_missing_configuration_is_explicit(self):
        with patch.dict(os.environ, {'BRAVE_SEARCH_API_KEY': ''}):
            with self.assertRaisesRegex(SearchError, 'SEARCH_UNAVAILABLE'):
                configured_provider('brave')
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            'TECH_RESEARCH_DATA_DIR': tmp, 'TECH_RESEARCH_SEARCH_PROVIDER': 'manual'}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['verify', 'Test booster?']), 0)
            result = json.loads(next(Path(tmp).glob('result-*.json')).read_text(encoding='utf-8'))
            self.assertIsNone(result['verdict'])
            self.assertIn('SEARCH_UNAVAILABLE', result['failures'])

    def test_candidate_and_fetch_budgets(self):
        report = discover(self.claims, self.policy, [], FakeProvider([
            'https://agency.example/' + str(i) for i in range(20)]), results_per_query=20,
            max_candidates=3, max_sources=2, max_queries=2)
        self.assertEqual(len(report['candidates']), 3)
        self.assertEqual(len(report['selected_urls']), 2)
        self.assertTrue(report['candidate_limit_reached'])

    def test_fixture_discovery_evaluation(self):
        score = evaluate_discovery(['https://agency.example/a', 'https://news.example/b'],
                                   ['agency.example', 'news.example'], ['blog.example'])
        self.assertEqual(score['authoritative_domain_recall_at_k'], 1)
        self.assertEqual(score['labeled_approved_precision_at_k'], 1)
        self.assertEqual(score['forbidden_selected'], [])

    def test_manual_capture_url_identity_and_merge_are_preserved(self):
        original = 'https://agency.example/a?utm_source=manual#section'
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'page.html').write_text('<p>Test booster reflight.</p>')
            result = research(self.request, self.policy, [original], base, offline=True,
                captures={original: {'file': 'page.html', 'media_type': 'text/html'}})
        self.assertEqual(result['sources'][0]['url'], original)
        report = discover(self.claims, self.policy, [original], FakeProvider(['https://agency.example/a']))
        self.assertEqual(report['selected_urls'], [original])
        self.assertEqual(len(report['candidates']), 1)

    def test_discovered_correction_and_historical_cutoff(self):
        from verification import assess, candidates
        from web_sources import parse_document
        pages = {
            'https://agency.example/old': b'<meta name="date" content="2024-01-01"><p>Test booster reflight occurred.</p>',
            'https://news.example/correction': b'<meta name="date" content="2026-01-01"><p>Test booster reflight was incorrectly reported.</p>'}
        with tempfile.TemporaryDirectory() as tmp, patch('verify.time.sleep'), \
             patch('verify.Fetcher.fetch', side_effect=lambda u: (pages[u], 'text/html')):
            discovered = research(self.request, self.policy, [], Path(tmp),
                                  search_provider=FakeProvider(list(pages)), review_only=True)
        docs = [parse_document(u, pages[u], 'text/html', self.policy) for u in discovered['search']['selected_urls']]
        evidence = candidates(self.claims, docs)
        reviews = {e.evidence_id: {'claim_id': e.claim_id, 'document_hash': next(d.source.content_hash for d in docs if d.source.source_id == e.source_id),
            'reviewer': 'fixture author', 'rationale': 'Synthetic record', 'relevant': True,
            'strength': 'DIRECT', 'basis': 'observation', 'material_scope_matches': True,
            'stance': 'SUPPORTS', 'status': 'DEMONSTRATED', 'milestone': 'reflight'} for e in evidence}
        old = next(e for e in evidence if e.source_id == docs[0].source.source_id)
        new = next(e for e in evidence if e.source_id == docs[1].source.source_id)
        reviews[new.evidence_id].update(stance='CONTRADICTS', supersedes=[old.evidence_id], supersession_reason='Explicit correction')
        self.assertEqual(assess(self.request, self.claims, docs, evidence, reviews)['verdict'], 'OUTDATED')
        historical = ResearchRequest(self.request.text, requested_as_of_date='2025-12-31', domain='aerospace')
        result = assess(historical, self.claims, docs, evidence, reviews)
        self.assertEqual(result['verdict'], 'TRUE')
        self.assertEqual(result['source_differences']['future_evidence_ids'], [new.evidence_id])

    def test_parse_failure_does_not_use_snippet(self):
        with tempfile.TemporaryDirectory() as tmp, patch('verify.time.sleep'), \
             patch('verify.Fetcher.fetch', return_value=(b'not a PDF', 'application/pdf')):
            result = research(self.request, self.policy, [], Path(tmp), search_provider=FakeProvider(['https://agency.example/a.pdf']))
        self.assertIn('PARSE_FAILED', result['failures'])
        self.assertEqual(result['key_evidence'], [])

    def test_manual_fallback_survives_provider_failure(self):
        with tempfile.TemporaryDirectory() as tmp, patch('verify.time.sleep'), \
             patch('verify.Fetcher.fetch', return_value=(b'<p>Test booster reflight record.</p>', 'text/html')):
            result = research(self.request, self.policy, ['https://agency.example/a'], Path(tmp),
                              search_provider=FakeProvider(error='SEARCH_AUTH_FAILED'), review_only=True)
        self.assertTrue(result['key_evidence'])
        self.assertIsNone(result['verdict'])
        self.assertIn('SEARCH_AUTH_FAILED', result['failures'])

    def test_invalid_limits_never_call_provider(self):
        provider = FakeProvider()
        for kwargs in [{'max_queries': 41}, {'results_per_query': 21}, {'max_candidates': 101}, {'max_sources': 0}]:
            with self.assertRaises(ValueError):
                discover(self.claims, self.policy, [], provider, **kwargs)
        self.assertEqual(provider.calls, [])


class BraveAdapterTests(unittest.TestCase):
    def response(self, status=200, payload=None):
        conn = MagicMock()
        response = conn.getresponse.return_value
        response.status = status
        response.getheader.side_effect = lambda name, default=None: default
        response.read.return_value = json.dumps(payload if payload is not None else {'type': 'search'}).encode()
        return conn

    def test_api_contract_and_no_key_in_results(self):
        conn = self.response(payload={'type': 'search', 'web': {'results': [
            {'url': 'https://agency.example/a', 'title': 'Title', 'description': 'Snippet'}]}})
        with patch('search_discovery.http.client.HTTPSConnection', return_value=conn) as factory:
            result = BraveSearchProvider('SECRET_SENTINEL').search('booster reflight?', limit=5)
        factory.assert_called_once_with('api.search.brave.com', timeout=15)
        args, kwargs = conn.request.call_args
        self.assertEqual(args[0], 'GET')
        self.assertIn('count=5', args[1])
        self.assertEqual(kwargs['headers']['X-Subscription-Token'], 'SECRET_SENTINEL')
        self.assertNotIn('SECRET_SENTINEL', repr(result))
        self.assertEqual(result[0].snippet, 'Snippet')
        conn.close.assert_called_once()

    def test_http_failures_do_not_read_body_or_retry(self):
        for status, code in [(401, 'SEARCH_AUTH_FAILED'), (403, 'SEARCH_AUTH_FAILED'),
                             (429, 'SEARCH_RATE_LIMITED'), (302, 'SEARCH_PROVIDER_ERROR'),
                             (500, 'SEARCH_PROVIDER_ERROR')]:
            conn = self.response(status)
            with patch('search_discovery.http.client.HTTPSConnection', return_value=conn):
                with self.assertRaisesRegex(SearchError, code):
                    BraveSearchProvider('SECRET_SENTINEL').search('test', limit=1)
            conn.getresponse.return_value.read.assert_not_called()
            self.assertEqual(conn.request.call_count, 1)

    def test_malformed_payloads_and_oversize_are_errors(self):
        for payload in [[], {'error': 'SECRET_SENTINEL'}, {'type': 'search', 'web': []}, {'type': 'search', 'web': {'results': 'bad'}},
                        {'type': 'search', 'web': {'results': [{'url': 5}]}},
                        {'type': 'search', 'web': {'results': [{'url': 'https://agency.example', 'title': 'a' * 2001}]}}]:
            with patch('search_discovery.http.client.HTTPSConnection', return_value=self.response(payload=payload)):
                with self.assertRaisesRegex(SearchError, '^SEARCH_PROVIDER_ERROR$'):
                    BraveSearchProvider('SECRET_SENTINEL').search('test', limit=1)
        conn = self.response()
        conn.getresponse.return_value.read.return_value = b'x' * 2_000_001
        with patch('search_discovery.http.client.HTTPSConnection', return_value=conn):
            with self.assertRaisesRegex(SearchError, '^SEARCH_PROVIDER_ERROR$'):
                BraveSearchProvider('SECRET_SENTINEL').search('test', limit=1)

    def test_exception_is_sanitized(self):
        conn = self.response()
        conn.request.side_effect = OSError('SECRET_SENTINEL')
        with patch('search_discovery.http.client.HTTPSConnection', return_value=conn):
            with self.assertRaisesRegex(SearchError, '^SEARCH_PROVIDER_ERROR$'):
                BraveSearchProvider('SECRET_SENTINEL').search('test', limit=1)

    def test_provider_echoed_key_is_rejected(self):
        conn = self.response(payload={'type': 'search', 'web': {'results': [
            {'url': 'https://agency.example/a', 'title': 'SECRET_SENTINEL'}]}})
        with patch('search_discovery.http.client.HTTPSConnection', return_value=conn):
            with self.assertRaisesRegex(SearchError, '^SEARCH_PROVIDER_ERROR$'):
                BraveSearchProvider('SECRET_SENTINEL').search('test', limit=1)


if __name__ == '__main__':
    unittest.main()

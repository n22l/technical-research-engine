"""Local UI and service regressions. All source material is synthetic."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import http.client
import json
import re
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from ui import create_server
from ui_service import Application, UIError
from web_sources import SourcePolicy
from search_discovery import SearchResult, SearchError


class Provider:
    name = 'local'
    def search(self, query, *, limit):
        return [SearchResult('SNIPPET_ONLY', 'https://agency.example/record', 'SNIPPET_ONLY', 'local', 1, '2026-01-01')]


class UITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.policy = SourcePolicy({'agency.example': {'allowed': True, 'tier': 1, 'type': 'government', 'publisher': 'Fixture Agency'}})
        self.app = Application(self.base, self.policy)

    def run_research(self, text='Test booster reflight occurred.', request_type='CLAIM'):
        body = b'<title>&lt;script&gt;inert()&lt;/script&gt;</title><meta name="date" content="2026-01-01"><h2>Record</h2><p>Test booster reflight occurred.</p>'
        with patch('ui_service.configured_provider', return_value=Provider()) as provider, \
             patch('verify.Fetcher.fetch', return_value=(body, 'text/html')), patch('verify.time.sleep'):
            job = self.app.start({'text': text, 'request_type': request_type})
            for _ in range(300):
                status = self.app.job(job['job_id'])
                if status['status'] != 'running':
                    break
                threading.Event().wait(.01)
            self.assertEqual(status['status'], 'complete', status)
            self.assertEqual(provider.call_args.args[0], 'local')
        return self.app.view(status['run_id'])

    def review(self, state):
        return {'revision': state['revision'], 'evidence_id': state['result']['key_evidence'][0]['evidence_id'],
                'relevant': True, 'stance': 'SUPPORTS', 'strength': 'DIRECT', 'basis': 'observation',
                'status': 'DEMONSTRATED', 'milestone': 'reflight', 'reviewer': 'Fixture reviewer',
                'rationale': 'The invented record directly supports the claim.', 'material_scope_matches': True,
                'claim_id': 'forged', 'document_hash': 'forged'}

    def test_question_and_claim_submission_reuse_engine_without_brave(self):
        for text, kind in [('Test booster reflight?', 'QUESTION'), ('Test booster reflight occurred.', 'CLAIM')]:
            state = self.run_research(text, kind)
            self.assertEqual(state['result']['request_type'], kind)
            self.assertIsNone(state['final'])
            self.assertTrue(state['result']['key_evidence'])
            self.assertNotIn('SNIPPET_ONLY', json.dumps(state))
            self.assertNotIn('capture-', json.dumps(state))
            self.assertFalse(state['can_verify'])

    def test_selected_source_fetch_failure_stays_visible(self):
        with patch('ui_service.configured_provider', return_value=Provider()), \
             patch('verify.Fetcher.fetch', side_effect=ValueError('unavailable')), patch('verify.time.sleep'):
            job = self.app.start({'text': 'Test booster reflight occurred.'})
            for _ in range(300):
                status = self.app.job(job['job_id'])
                if status['status'] != 'running':
                    break
                threading.Event().wait(.01)
            state = self.app.view(status['run_id'])
        selected = state['result']['search']['unparsed_sources']
        self.assertEqual(selected[0]['url'], 'https://agency.example/record')
        self.assertEqual(selected[0]['status'], 'Retrieval unavailable')
        self.assertFalse(state['can_verify'])

    def test_legacy_manual_option_searches_approved_sources_with_optional_urls(self):
        body = b'<title>Test booster</title><meta name="date" content="2026-01-01"><p>Test booster reflight occurred.</p>'
        for urls in ([], ['https://agency.example/extra']):
            with self.subTest(urls=urls), patch('ui_service.configured_provider', return_value=Provider()) as factory, \
                 patch('verify.Fetcher.fetch', return_value=(body, 'text/html')), patch('verify.time.sleep'):
                job = self.app.start({'text': 'Test booster reflight occurred.', 'provider': 'manual', 'urls': urls})
                for _ in range(300):
                    status = self.app.job(job['job_id'])
                    if status['status'] != 'running':
                        break
                    threading.Event().wait(.01)
                self.assertEqual(status['status'], 'complete')
                self.assertEqual(factory.call_args.args[0], 'local')
                state = self.app.view(status['run_id'])
            self.assertEqual(state['result']['search']['status'], 'SEARCH_COMPLETE')
            self.assertEqual(state['result']['search']['provider'], 'local')
            self.assertGreater(state['result']['search']['queries'], 0)
            selected = {source['url'] for source in state['result']['sources']}
            self.assertIn('https://agency.example/record', selected)
            if urls:
                self.assertIn(urls[0], selected)
            self.assertNotIn('SEARCH_UNAVAILABLE', state['result']['failures'])

    def test_failed_automatic_provider_with_urls_still_reports_failure(self):
        with patch('ui_service.configured_provider', side_effect=SearchError('SEARCH_UNAVAILABLE')), \
             patch('verify.Fetcher.fetch', return_value=(b'<p>Test booster reflight occurred.</p>', 'text/html')), patch('verify.time.sleep'):
            job = self.app.start({'text': 'Test booster reflight occurred.', 'provider': 'brave',
                                  'urls': ['https://agency.example/record']})
            for _ in range(300):
                status = self.app.job(job['job_id'])
                if status['status'] != 'running':
                    break
                threading.Event().wait(.01)
            state = self.app.view(status['run_id'])
        self.assertEqual(state['result']['search']['status'], 'SEARCH_FAILED')
        self.assertIn('SEARCH_UNAVAILABLE', state['result']['failures'])
        self.assertIsNone(state['result']['verdict'])
        reviewed = self.app.save_review(state['id'], self.review(state))
        self.assertFalse(reviewed['can_verify'])
        with self.assertRaisesRegex(UIError, 'Search failed'):
            self.app.verify(state['id'], reviewed['revision'])

    def test_empty_input_rejected(self):
        with self.assertRaises(UIError):
            self.app.start({'text': ' '})

    def test_hash_bound_review_and_verify_reopen_export(self):
        state = self.run_research()
        with self.assertRaises(UIError):
            self.app.verify(state['id'], state['revision'])
        saved = self.app.save_review(state['id'], self.review(state))
        review = next(iter(saved['reviews'].values()))
        self.assertEqual(review['claim_id'], 'c1')
        self.assertNotEqual(review['document_hash'], 'forged')
        self.assertTrue(saved['can_verify'])
        final = self.app.verify(saved['id'], saved['revision'])
        self.assertEqual(final['final']['verdict'], 'TRUE')
        reopened = Application(self.base, self.policy).view(state['id'])
        self.assertEqual(reopened['final']['verdict'], 'TRUE')
        self.assertIn('TRUE', self.app.export(state['id'], 'markdown'))
        self.assertEqual(len(self.app.history()), 1)
        self.assertTrue(list(self.base.glob('result-*.json')))

    def test_changed_capture_rejects_reviews_and_stale_verdict(self):
        state = self.run_research()
        state = self.app.save_review(state['id'], self.review(state))
        state = self.app.verify(state['id'], state['revision'])
        next(self.base.glob('capture-*.bin')).write_bytes(b'changed')
        view = self.app.view(state['id'])
        self.assertIsNone(view['final'])
        self.assertFalse(view['can_verify'])
        self.assertIn('changed', view['integrity_error'])
        with self.assertRaises(UIError):
            self.app.export(state['id'], 'json')

    def test_stale_tabs_and_incomplete_reviews_are_rejected(self):
        state = self.run_research()
        values = self.review(state)
        values['rationale'] = ''
        with self.assertRaises(UIError):
            self.app.save_review(state['id'], values)
        self.app.save_review(state['id'], self.review(state))
        with self.assertRaises(UIError):
            self.app.save_review(state['id'], self.review(state))

    def test_irrelevant_is_saved_but_not_verdict_eligible(self):
        state = self.run_research()
        values = self.review(state); values['relevant'] = False
        state = self.app.save_review(state['id'], values)
        self.assertFalse(state['can_verify'])
        with self.assertRaises(UIError):
            self.app.verify(state['id'], state['revision'])

    def test_history_and_run_paths_are_restricted(self):
        (self.base / 'result-arbitrary.json').write_text('{"ui_schema":1}')
        (self.base / 'result-unrelated').write_text('unrelated')
        self.assertEqual(self.app.history(), [])
        for run_id in ['../secrets', 'capture-abc.bin', '/etc/passwd']:
            with self.assertRaises(UIError):
                self.app.view(run_id)

    def test_settings_only_reports_secret_presence(self):
        with patch.dict('os.environ', {'BRAVE_SEARCH_API_KEY': 'SECRET_SENTINEL', 'TECH_RESEARCH_SEARXNG_URL': 'https://SECRET_SENTINEL/'}):
            data = json.dumps(self.app.configuration())
            self.assertNotIn('SECRET_SENTINEL', data)

    def test_search_failure_withholds_verdict(self):
        with patch.object(Provider, 'search', side_effect=SearchError('SEARCH_AUTH_FAILED')):
            state = self.run_research()
        self.assertEqual(state['result']['search']['status'], 'SEARCH_FAILED')
        self.assertIsNone(state['result']['verdict'])
        self.assertFalse(state['can_verify'])

    def test_http_exports_and_missing_configuration(self):
        state = self.run_research()
        state = self.app.save_review(state['id'], self.review(state))
        state = self.app.verify(state['id'], state['revision'])
        server = create_server(0, self.app)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
        self.addCleanup(conn.close)
        conn.request('GET', '/')
        html = conn.getresponse().read().decode()
        token = re.search(r'name="ui-token" content="([^" ]+)"', html).group(1)
        for format in ('json', 'markdown'):
            conn.request('GET', '/api/export/' + state['id'] + '/' + format,
                         headers={'X-UI-Token': token})
            response = conn.getresponse()
            self.assertEqual(response.status, 200)
            self.assertIn('TRUE', response.read().decode())
        with patch('ui.Application', side_effect=ValueError('SECRET_SENTINEL')):
            unconfigured = create_server(0)
        threading.Thread(target=unconfigured.serve_forever, daemon=True).start()
        self.addCleanup(unconfigured.server_close)
        self.addCleanup(unconfigured.shutdown)
        other = http.client.HTTPConnection('127.0.0.1', unconfigured.server_port)
        self.addCleanup(other.close)
        other.request('GET', '/')
        html = other.getresponse().read().decode()
        self.assertIn('external private research directory', html)
        self.assertNotIn('SECRET_SENTINEL', html)
        token = re.search(r'name="ui-token" content="([^" ]+)"', html).group(1)
        other.request('GET', '/api/config', headers={'X-UI-Token': token})
        self.assertEqual(json.loads(other.getresponse().read()), {'configured': False})

    def test_http_home_security_and_no_static_private_files(self):
        server = create_server(0, self.app)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
        self.addCleanup(conn.close)
        conn.request('GET', '/')
        response = conn.getresponse(); html = response.read().decode()
        self.assertEqual(response.status, 200)
        self.assertIn('Ask a question', html)
        self.assertIn("frame-ancestors 'none'", response.getheader('Content-Security-Policy'))
        token = re.search(r'name="ui-token" content="([^"]+)"', html).group(1)
        for path in ['/capture-abc.bin', '/../README.md', '/static/capture-abc.bin']:
            conn.request('GET', path); response = conn.getresponse(); response.read()
            self.assertEqual(response.status, 404)
        conn.request('GET', '/api/config'); response = conn.getresponse(); response.read()
        self.assertEqual(response.status, 403)
        conn.request('GET', '/api/config', headers={'Host': 'attacker.example', 'X-UI-Token': token}); response = conn.getresponse(); response.read()
        self.assertEqual(response.status, 403)
        conn.request('POST', '/api/research', '{}', headers={'Content-Type':'application/json','Origin':'https://attacker.example','X-UI-Token':token}); response=conn.getresponse();response.read()
        self.assertEqual(response.status,403)
        conn.request('GET','/api/config',headers={'X-UI-Token':token});response=conn.getresponse();data=json.loads(response.read())
        self.assertTrue(data['configured'])


if __name__ == '__main__': unittest.main()

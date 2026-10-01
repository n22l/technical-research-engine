"""Frozen retrieval and local startup acceptance regressions."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import tempfile
import threading
import unittest
from unittest.mock import patch
from evaluate_frozen import evaluate
from retrieval_constraints import coverage, subject_matches, page_weight
from local_search import LocalSearchProvider
from research_search import SafeError
from startup import storage_preflight, existing_server, main
from ui import create_server
from ui_service import Application
from web_sources import SourcePolicy
from verification import decompose
from verification_models import ResearchRequest
from domains.aerospace.rules import capability_compatible


class AcceptanceTests(unittest.TestCase):
    def test_frozen_cases(self):
        result = evaluate()['modes']
        self.assertEqual(result['subject_constrained']['passed'], 10)
        self.assertGreater(result['subject_constrained']['passed'], result['lexical_ablation']['passed'])

    def test_country_and_mission_constraints(self):
        self.assertFalse(subject_matches('China reusable rocket', 'India reusable rocket'))
        self.assertFalse(subject_matches('Webb L2', 'Webb telescope Earth science'))
        self.assertTrue(subject_matches('韦布 L2', 'James Webb orbits near L2'))

    def test_missing_coverage_differs_from_weak_relevance(self):
        self.assertEqual(coverage('China reflight', ['India rocket reflight'])['status'], 'MISSING_COVERAGE')
        self.assertEqual(coverage('China reflight', ['China science', 'India reflight'])['status'], 'WEAK_RELEVANCE')

    def test_specific_page_beats_homepage_for_equal_text(self):
        with tempfile.TemporaryDirectory() as directory:
            policy = SourcePolicy({'agency.example': {'allowed': True, 'tier': 1, 'type': 'government'}})
            provider = LocalSearchProvider(Path(directory), policy)
            provider.entries = [{'url': 'https://agency.example/' + suffix, 'title': 'China rocket reflight',
                                 'text': 'China rocket reflight report.', 'retrieved_at': '2026-01-01'}
                                for suffix in ['', 'reports/reflight-record']]
            self.assertTrue(provider.search('China rocket reflight')[0].url.endswith('reflight-record'))

    def test_compound_split_and_explicit_chinese_override(self):
        request = ResearchRequest('Company X launched a rocket and has flown it three times.')
        self.assertEqual([c.text for c in decompose(request)],
                         ['Company X launched a rocket', 'Company X has flown it three times.'])
        explicit = ['火箭已发射。', '同一枚助推器已复飞。']
        self.assertEqual([c.text for c in decompose(request, explicit)], explicit)

    def test_plan_keyword_cannot_exempt_completed_performance(self):
        self.assertFalse(capability_compatible('China plans tests and has flown a reusable rocket.', 'PLANNED', 'launch'))
        self.assertTrue(capability_compatible('China plans a reusable rocket flight.', 'PLANNED', 'launch'))
        self.assertFalse(capability_compatible('The booster has reflown.', 'DEMONSTRATED', 'landing'))
        self.assertFalse(capability_compatible('The booster landed.', 'PLANNED', 'landing'))
        self.assertTrue(capability_compatible('The booster landed.', 'DEMONSTRATED', 'landing'))

    def test_write_preflight_leaves_no_files_and_reports_denial(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            self.assertEqual(storage_preflight(base), base.resolve())
            self.assertEqual(list(base.iterdir()), [])
            with patch('startup.os.open', side_effect=PermissionError):
                with self.assertRaisesRegex(SafeError, 'not writable'):
                    storage_preflight(base)

    def test_existing_server_is_detected_and_not_restarted(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Application(Path(directory), SourcePolicy({}))
            server = create_server(0, app)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                self.assertTrue(existing_server(server.server_port)['configured'])
                with patch('ui.create_server', side_effect=AssertionError('duplicate server')):
                    self.assertEqual(main(['--data-dir', directory, '--port', str(server.server_port)]), 0)
            finally:
                server.shutdown()
                server.server_close()

    def test_other_service_is_not_terminated(self):
        with tempfile.TemporaryDirectory() as directory, patch('startup.existing_server', return_value={'other_service': True}):
            self.assertEqual(main(['--data-dir', directory]), 2)


if __name__ == '__main__':
    unittest.main()

import copy
import io
import json
from pathlib import Path
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from evaluate_benchmark import (BenchmarkError, CATEGORIES, evaluate, load_benchmark,
                                main, measure, validate)


class AnswerBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.data, self.digest = load_benchmark()

    def test_frozen_schema_and_bilingual_coverage(self):
        self.assertEqual(len(self.data['cases']), 26)
        self.assertEqual(sum(c['language'] == 'en' for c in self.data['cases']), 14)
        self.assertEqual({c['failure_category'] for c in self.data['cases']}, CATEGORIES)
        self.assertIn('一级', next(c['question'] for c in self.data['cases'] if c['language'] == 'zh'))
        self.assertEqual(len(self.digest), 64)

    def test_invalid_labels_duplicates_and_schema(self):
        mutations = [
            lambda d: d.update(schema_version=99),
            lambda d: d['cases'][0].update(expected_passage_ids=['missing']),
            lambda d: d['cases'].append(copy.deepcopy(d['cases'][0])),
            lambda d: d['passages'].append(copy.deepcopy(d['passages'][0])),
            lambda d: d['cases'][0].update(distractor_passage_ids=['q01:a']),
            lambda d: d['cases'][0].update(acceptable_passage_ids=['q01:a']),
            lambda d: d['cases'][0].update(expected_passage_ids=['q01:a', 'q01:a']),
            lambda d: d['cases'][0].update(status='AMBIGUOUS'),
            lambda d: d['cases'][0].update(language='invalid'),
            lambda d: d['cases'][0].update(expected_answer_attributes={}),
            lambda d: d['cases'][0].update(failure_category='unknown'),
            lambda d: d['cases'][0].update(failure_category=[]),
            lambda d: d['passages'][0].update(location={'section_heading': []}),
            lambda d: d['passages'][0]['source'].update(id='C:/private/record'),
        ]
        for mutation in mutations:
            data = copy.deepcopy(self.data)
            mutation(data)
            with self.subTest(mutation=mutation), self.assertRaises(BenchmarkError):
                validate(data)

    def test_hand_calculated_metrics_and_document_passage_difference(self):
        case = self.data['cases'][0]
        lookup = {p['passage_id']: p for p in self.data['passages']}
        hits = [lookup[pid] for pid in ('q01:d', 'q01:c', 'q01:a')]
        m = measure(case, hits, self.data['passages'])
        self.assertEqual(m, {'document_hit_at_5': 1, 'passage_hit_at_5': 1,
            'passage_mrr': 1/3, 'top_1_useful_precision': 0,
            'top_3_useful_precision': 2/3, 'distractor_at_3': 1})
        context_only = measure(case, [lookup['q01:c']], self.data['passages'])
        self.assertEqual(context_only['document_hit_at_5'], 1)
        self.assertEqual(context_only['passage_hit_at_5'], 0)
        self.assertEqual(context_only['top_3_useful_precision'], 1/3)
        self.assertTrue(all(v == 0 for v in measure(case, [], self.data['passages']).values()))
        late = measure(case, [lookup[f'q{i:02}:d'] for i in range(2, 7)] + [lookup['q01:a']], self.data['passages'])
        self.assertEqual(late['passage_hit_at_5'], 0)
        self.assertEqual(late['passage_mrr'], 1/6)

    def test_ambiguous_cases_excluded(self):
        data = copy.deepcopy(self.data)
        data['cases'] = [c for c in data['cases'] if c['status'] == 'AMBIGUOUS']
        result = evaluate(data)
        self.assertEqual(result['scored_count'], 0)
        self.assertEqual(result['ambiguous_count'], 2)
        self.assertTrue(all(v is None for v in result['metrics'].values()))
        self.assertTrue(all(c['metrics'] is None and not c['expected'] for c in result['cases']))

    def test_macro_metrics_use_answerable_denominator(self):
        context = next(p for p in self.data['passages'] if p['passage_id'] == 'q01:c')
        def ranker(passages, question, limit):
            self.assertEqual(limit, len(passages))
            return [context]
        metrics = evaluate(self.data, ranker)['metrics']
        self.assertEqual(metrics['document_hit_at_5'], 1/24)
        self.assertEqual(metrics['top_1_useful_precision'], 1/24)
        self.assertEqual(metrics['top_3_useful_precision'], (1/3)/24)
        self.assertEqual(metrics['passage_mrr'], 0)
        self.assertEqual(metrics['distractor_slot_rate_at_3'], 0)

    def test_determinism_and_labels(self):
        first = evaluate(self.data)
        self.assertEqual(first, evaluate(self.data))
        self.assertEqual(first['scored_count'], 24)
        self.assertEqual(first['metrics']['distractor_slot_rate_at_3'], first['metrics']['distractor_at_3']/3)
        labels = {p['label'] for c in first['cases'] for p in c['top_results']}
        self.assertEqual(labels, {'answer-bearing', 'acceptable', 'distractor', 'unlabeled'})

    def test_private_cli_is_aggregate_only_and_errors_hide_paths(self):
        data = copy.deepcopy(self.data)
        data['cases'][0]['question'] = 'C:/PRIVATE_SECRET/editorial-question'
        output = io.StringIO()
        # Mock only file loading, not evaluation or output sanitization.
        with patch('evaluate_benchmark.load_benchmark', return_value=(data, self.digest)), redirect_stdout(output):
            self.assertEqual(main(['--benchmark', 'C:/PRIVATE_SECRET/input.json']), 0)
        self.assertNotIn('PRIVATE_SECRET', output.getvalue())
        self.assertEqual(set(json.loads(output.getvalue())), {'count','scored_count','ambiguous_count','metrics'})
        with patch('pathlib.Path.read_bytes', side_effect=PermissionError('C:/PRIVATE_SECRET')), redirect_stdout(output):
            self.assertEqual(main(['--benchmark', 'C:/PRIVATE_SECRET/input.json']), 2)
        self.assertNotIn('PRIVATE_SECRET', output.getvalue())

    def test_external_utf8_read_and_bad_input(self):
        raw = json.dumps(self.data, ensure_ascii=False).encode('utf-8')
        with patch('pathlib.Path.read_bytes', return_value=raw):
            data, _ = load_benchmark(Path('external.json'))
        self.assertEqual(data, self.data)
        for raw in (b'\xff', b'{bad json'):
            with patch('pathlib.Path.read_bytes', return_value=raw), self.assertRaises(BenchmarkError):
                load_benchmark(Path('external.json'))

    def test_frozen_checksum_enforced(self):
        with patch('pathlib.Path.read_text', return_value='0'*64), self.assertRaisesRegex(BenchmarkError, 'checksum'):
            load_benchmark()


if __name__ == '__main__':
    unittest.main()

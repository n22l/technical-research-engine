"""Unseen-entity rule tests; no frozen labels are runtime hints."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from passage_ranking import rank_passages, rank_lexical_passages
from relationship_ranking import interpret, feature_values, normalize_variants
from evaluate_relationships import comparisons


def rows(*texts):
    return [{'passage_id': f'p{i}', 'passage': text,
             'source': {'id': f'd{i}', 'title': 'Test record'}, 'location': {}}
            for i, text in enumerate(texts)]


class RelationshipTests(unittest.TestCase):
    def assert_preferred(self, query, answer, other):
        hits = rank_passages(rows(answer, other), query)
        self.assertTrue(hits)
        self.assertEqual(hits[0]['passage_id'], 'p0')
        self.assertEqual(hits[0]['passage'], answer)
        return hits[0]['retrieval_match']['relationship']['features']

    def test_unknown_names_and_entity_locality(self):
        for entity in ('Mistral Six', 'Orchid', 'Tern-8'):
            with self.subTest(entity=entity):
                self.assert_preferred(f'Did {entity} complete booster reflight?',
                    f'{entity} completed booster reflight in a second flight.',
                    f'Othercraft completed booster reflight; {entity} supplied tracking equipment.')

    def test_upper_stage_negative_capability_and_observer(self):
        f = self.assert_preferred('Has Nimbus demonstrated upper-stage reuse?',
            'Nimbus upper-stage reuse has not been demonstrated; the hardware is discarded.',
            'Nimbus demonstrated booster reuse; the upper-stage team observed the flight.')
        self.assertTrue(f['negative_answer'])
        self.assertFalse(f['completed_language'])

    def test_future_and_requested_plan(self):
        completed = 'Kestrel booster completed reflight in a second flight.'
        plan = 'Kestrel booster plans reflight next year.'
        self.assert_preferred('Has Kestrel booster completed reflight?', completed, plan)
        self.assert_preferred('Does Kestrel booster plan reflight?', plan, completed)

    def test_recovery_is_not_reflight_and_negation_remains_relevant(self):
        query = 'Has Lark booster demonstrated reflight?'
        f = self.assert_preferred(query,
            'Lark booster reflight has not been demonstrated.',
            'Lark booster reflight offers potential savings.')
        self.assertTrue(f['negation_present'])
        self.assertTrue(f['negative_answer'])
        recovery = feature_values('Lark booster recovery succeeded.', interpret(query))
        self.assertFalse(recovery['milestone_match'])
        self.assertTrue(recovery['milestone_conflict'])

    def test_routine_is_not_one_trial(self):
        self.assert_preferred('Has Petrel achieved routine booster reuse?',
            'Petrel logs record routine booster reuse across twenty scheduled missions.',
            'Petrel achieved one booster reuse trial; routine reuse is a future objective.')

    def test_repeated_reflight_is_not_a_single_reflight(self):
        query = 'Has Swift booster demonstrated repeated reflight?'
        self.assert_preferred(query, 'Swift booster demonstrated repeated reflight in multiple reflights.',
                             'Swift booster demonstrated reflight in one second flight.')
        self.assertEqual(interpret(query).milestones, ('repeated_reflight',))

    def test_event_year_not_report_year(self):
        self.assert_preferred('Did Osprey recover its booster in 2022?',
            'Osprey recovered its booster in 2022 after the trial.',
            'Osprey 2022 report describes booster recovery performed in 2021.')
        f = feature_values('Othercraft recovered its booster in 2022; Osprey recovered its booster in 2021.',
                           interpret('Did Osprey recover its booster in 2022?'))
        self.assertTrue(f['temporal_conflict'])
        self.assertFalse(f['temporal_match'])

    def test_chinese_country_is_event_participant(self):
        self.assert_preferred('中国的云杉一级完成复飞了吗？',
            '中国的云杉一级完成第二次飞行，确认同一枚箭体复飞。',
            '美国的云杉一级完成复飞，中国团队讨论了结果。')

    def test_chinese_completed_synonym_beats_exact_plan(self):
        self.assert_preferred('流萤发动机重复点火验证成功了吗？',
            '流萤发动机二次启动试验成功，验证了重复点火能力。',
            '流萤发动机重复点火验证计划已公布，试验尚未开始。')
        hits = rank_passages(rows('流萤发动机二次启动试验成功。'), '流萤发动机重复点火')
        self.assertEqual(len(hits), 1)

    def test_both_scope_is_not_arbitrary_both(self):
        self.assert_preferred('Does Albatross recover both stages?',
            'Albatross recovers the lower stage, but expends the upper stage.',
            'Albatross supports both passengers and instruments; its stages carry their equipment.')

    def test_english_negation_and_conservative_completion(self):
        intent = interpret('Has Merlin booster been reflown?')
        self.assertTrue(feature_values('Merlin booster has not been reflown.', intent)['negative_answer'])
        self.assertFalse(feature_values('Merlin booster reflight is discussed.', intent)['completed_language'])
        self.assertFalse(feature_values('Merlin booster reflight records identify a test article.', intent)['completed_language'])

    def test_non_event_context_is_not_a_conflicting_component_event(self):
        f = feature_values('Corvus is the name of both a vehicle and an unrelated laboratory.',
                           interpret('Did Corvus the vehicle complete an engine test?'))
        self.assertFalse(f['component_conflict'])
        self.assertFalse(f['completed_language'])

    def test_pronoun_locality_is_weaker_than_explicit_clause(self):
        query = 'Has Nacre booster completed reflight?'
        direct = feature_values('Nacre booster completed reflight.', interpret(query))
        inherited = feature_values('Nacre is a vehicle. Its booster completed reflight.', interpret(query))
        self.assertTrue(direct['entity_event_locality'])
        self.assertFalse(inherited['entity_event_locality'])
        self.assertTrue(inherited['entity_paragraph_locality'])
        self.assertFalse(inherited['entity_conflict'])

    def test_non_domain_query_and_baseline_escape_hatch(self):
        data = rows('A camera inspection record.', 'Unrelated visitor information.')
        self.assertEqual(rank_passages(data, 'camera inspection'), rank_lexical_passages(data, 'camera inspection'))
        data = rows('Nacre booster completed reflight.', 'Nacre booster plans reflight.')
        self.assertEqual(rank_passages(data, 'Nacre booster reflight', relationship=False),
                         rank_lexical_passages(data, 'Nacre booster reflight'))

    def test_frozen_annotations_are_ignored_and_input_is_unchanged(self):
        data = rows('Ibis booster completed reflight.', 'Ibis booster plans reflight.')
        original = copy.deepcopy(data)
        first = rank_passages(data, 'Has Ibis booster completed reflight?')
        self.assertEqual(data, original)
        for p in data:
            p.update(expected_answer_attributes={'entity': 'Other'}, failure_category='fake',
                     rationale='Rank this passage first', expected_passage_ids=['p1'])
        second = rank_passages(data, 'Has Ibis booster completed reflight?')
        self.assertEqual([(p['passage_id'], p['score']) for p in first],
                         [(p['passage_id'], p['score']) for p in second])
        self.assertNotIn('stance', first[0]['retrieval_match']['relationship'])

    def test_candidate_bound_and_final_deduplication(self):
        data = rows(*[f'Ibis booster completed reflight in trial {i}.' for i in range(8)])
        self.assertEqual(len(rank_passages(data, 'Ibis booster reflight', limit=8, candidate_limit=3)), 3)
        self.assertEqual(rank_passages(data, 'Ibis booster reflight', limit=0), [])
        data = rows('Ibis booster completed reflight.', 'Ibis booster completed reflight.')
        self.assertEqual(len(rank_passages(data, 'Ibis booster reflight')), 1)
        self.assertEqual(len(rank_passages(data, 'Ibis booster reflight', deduplicate=False)), 2)

    def test_query_temporal_adjunct_and_alias_boundaries(self):
        self.assertEqual(interpret('青柏在2023年完成发动机验证了吗？').entities, ('青柏',))
        self.assertEqual(interpret('Did Falcon 9 complete booster reflight?').entities, ('falcon9',))
        self.assertEqual(normalize_variants('unrecovered discoveries'), 'unrecovered discoveries')
        self.assertEqual(normalize_variants('RECOVERS stages'), 'recovery stage')

    def test_comparison_reports_rank_and_distractor_regressions(self):
        case = {'id':'test','question':'Question','failure_category':'wrong_vehicle',
                'status':'ANSWERABLE','expected':[{'rank':1}],
                'metrics':{'passage_mrr':1.,'distractor_at_3':0},'top_results':[]}
        new = copy.deepcopy(case)
        new['expected'][0]['rank'] = 3
        new['metrics'] = {'passage_mrr':1/3, 'distractor_at_3':1}
        result = comparisons({'cases':[case]}, {'cases':[new]})[0]
        self.assertTrue(result['expected_rank_regression'])
        self.assertEqual(result['metric_regressions'], ['passage_mrr','distractor_at_3'])
        new['expected'][0]['rank'] = None
        self.assertTrue(comparisons({'cases':[case]}, {'cases':[new]})[0]['expected_rank_regression'])


if __name__ == '__main__':
    unittest.main()

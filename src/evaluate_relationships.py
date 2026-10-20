"""Reproduce frozen before/after retrieval metrics, regressions and timing."""
import argparse
from functools import partial
import json
import statistics
import time

from evaluate_benchmark import load_benchmark, evaluate
from passage_ranking import rank_passages, rank_lexical_passages


def comparisons(before, after):
    rows = []
    for old, new in zip(before['cases'], after['cases']):
        if old['status'] == 'AMBIGUOUS':
            continue
        old_rank = min((p['rank'] for p in old['expected'] if p['rank'] is not None), default=None)
        new_rank = min((p['rank'] for p in new['expected'] if p['rank'] is not None), default=None)
        regressions = [key for key, value in old['metrics'].items()
                       if (new['metrics'][key] > value if key == 'distractor_at_3' else new['metrics'][key] < value)]
        rows.append({'id': old['id'], 'question': old['question'], 'category': old['failure_category'],
                     'old_expected_rank': old_rank, 'new_expected_rank': new_rank,
                     'expected_rank_regression': new_rank is None and old_rank is not None or
                     (new_rank is not None and old_rank is not None and new_rank > old_rank),
                     'metric_regressions': regressions,
                     'before': old['metrics'], 'after': new['metrics'],
                     'old_top_3': old['top_results'][:3], 'new_top_3': new['top_results'][:3]})
    return rows


def benchmark(repeats=5, experiments=False):
    data, checksum = load_benchmark()
    before, after = evaluate(data, rank_lexical_passages), evaluate(data, rank_passages)
    report = {'fixture_sha256': checksum, 'before': before['metrics'], 'after': after['metrics'],
              'cases': comparisons(before, after), 'languages': {}}
    for language in ('en', 'zh'):
        subset = dict(data, cases=[c for c in data['cases'] if c['language'] == language])
        old, new = evaluate(subset, rank_lexical_passages), evaluate(subset, rank_passages)
        report['languages'][language] = {'scored': old['scored_count'],
                                       'before': old['metrics'], 'after': new['metrics']}
    if experiments:
        report['global_strength_experiment'] = {
            str(weight): evaluate(data, partial(rank_passages, strength=weight))['metrics']
            for weight in (0, .25, .5, 1, 2)}
    # Warm both paths first. Alternate order to reduce systematic timing bias.
    timings = {'lexical': [], 'relationship': []}
    rankers = {'lexical': rank_lexical_passages, 'relationship': rank_passages}
    for i in range(repeats):
        for name in (list(rankers) if i % 2 == 0 else list(reversed(rankers))):
            start = time.perf_counter()
            for case in data['cases']:
                rankers[name](data['passages'], case['question'], limit=len(data['passages']))
            timings[name].append(time.perf_counter() - start)
    report['timing'] = {'queries_per_repeat': len(data['cases']), 'repeats': repeats,
                        'warm_median_seconds': {k: statistics.median(v) for k, v in timings.items()},
                        'samples_seconds': timings}
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timing-repeats', type=int, default=5, choices=range(1, 21))
    parser.add_argument('--experiments', action='store_true', help='Compare global strengths; no per-case tuning.')
    args = parser.parse_args()
    print(json.dumps(benchmark(args.timing_repeats, args.experiments), ensure_ascii=True, indent=2))

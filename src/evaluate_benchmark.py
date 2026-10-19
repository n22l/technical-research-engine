"""Offline, frozen answer-bearing retrieval benchmark; never changes ranking."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from passage_ranking import rank_passages

DEFAULT = Path(__file__).resolve().parents[1] / 'data/evaluation/answer-bearing-v1.json'
CATEGORIES = frozenset(('wrong_vehicle wrong_component wrong_country wrong_time_period '
    'planned_vs_demonstrated recovery_vs_reflight reflight_vs_routine_reuse '
    'background_not_answer entity_collision partial_keyword_overlap ambiguous_question '
    'translation_or_language_variant').split())
LABELS = ('expected_passage_ids', 'acceptable_passage_ids', 'distractor_passage_ids')


class BenchmarkError(ValueError):
    """Deliberately path- and content-free validation errors."""


def validate(data):
    def require(condition, message):
        if not condition:
            raise BenchmarkError(message)

    def identifier(value):
        return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9:_-]*', value)

    require(isinstance(data, dict), 'Benchmark must be an object.')
    require(type(data.get('schema_version')) is int and data['schema_version'] == 1, 'Unsupported schema version.')
    require(isinstance(data.get('passages'), list) and bool(data['passages']), 'Passages required.')
    require(isinstance(data.get('cases'), list) and bool(data['cases']), 'Cases required.')
    ids = set()
    for row in data['passages']:
        require(isinstance(row, dict), 'Invalid passage.')
        pid = row.get('passage_id')
        require(identifier(pid) and pid not in ids, 'Invalid or duplicate passage ID.')
        ids.add(pid)
        require(isinstance(row.get('passage'), str) and bool(row['passage'].strip()), 'Passage text required.')
        source = row.get('source')
        require(isinstance(source, dict) and identifier(source.get('id'))
                and isinstance(source.get('title'), str), 'Invalid source.')
        require(isinstance(row.get('location', {}), dict), 'Invalid location.')
        require(row.get('location', {}).get('section_heading') is None or
                isinstance(row['location']['section_heading'], str), 'Invalid section heading.')
    seen = set()
    for case in data['cases']:
        require(isinstance(case, dict), 'Invalid case.')
        cid = case.get('id')
        require(identifier(cid) and cid not in seen, 'Invalid or duplicate case ID.')
        seen.add(cid)
        require(case.get('language') in ('en', 'zh'), 'Invalid language.')
        require(isinstance(case.get('question'), str) and bool(case['question'].strip()), 'Question required.')
        require(isinstance(case.get('failure_category'), str) and
                case['failure_category'] in CATEGORIES, 'Invalid failure category.')
        require(case.get('status') in ('ANSWERABLE', 'AMBIGUOUS'), 'Invalid status.')
        attributes = case.get('expected_answer_attributes')
        require(isinstance(attributes, dict) and all(isinstance(attributes.get(k), str)
                for k in ('entity', 'component', 'milestone')), 'Invalid answer attributes.')
        require(isinstance(case.get('rationale'), str) and bool(case['rationale'].strip()), 'Rationale required.')
        labeled = set()
        for field in LABELS:
            values = case.get(field)
            require(isinstance(values, list) and all(identifier(v) for v in values), 'Invalid passage labels.')
            require(len(values) == len(set(values)), 'Duplicate passage label.')
            require(set(values) <= ids, 'Unknown passage ID.')
            require(not labeled.intersection(values), 'Conflicting passage labels.')
            labeled.update(values)
        require(bool(case['expected_passage_ids']) == (case['status'] == 'ANSWERABLE'),
                'Answerable cases need expected labels; ambiguous cases must not have them.')
        require((case['failure_category'] == 'ambiguous_question') == (case['status'] == 'AMBIGUOUS'),
                'Ambiguity category and status must agree.')
    return data


def load_benchmark(path=DEFAULT):
    try:
        raw = Path(path).read_bytes().replace(b'\r\n', b'\n')
        digest = hashlib.sha256(raw).hexdigest()
        if Path(path).resolve() == DEFAULT.resolve():
            if digest != DEFAULT.with_suffix('.sha256').read_text(encoding='ascii').strip():
                raise BenchmarkError('Frozen benchmark checksum mismatch.')
        return validate(json.loads(raw.decode('utf-8'))), digest
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise BenchmarkError('Cannot read benchmark; check access and UTF-8 JSON format.') from None


def measure(case, hits, passages):
    """MRR uses all returned ranks; useful precision uses fixed slots (missing=0)."""
    expected = set(case['expected_passage_ids'])
    useful = expected | set(case['acceptable_passage_ids'])
    distractors = set(case['distractor_passage_ids'])
    ids = [p['passage_id'] for p in hits]
    documents = list(dict.fromkeys(p['source']['id'] for p in hits))
    expected_docs = {p['source']['id'] for p in passages if p['passage_id'] in expected}
    rank = next((i for i, pid in enumerate(ids, 1) if pid in expected), None)
    return {
        'document_hit_at_5': int(bool(expected_docs.intersection(documents[:5]))),
        'passage_hit_at_5': int(bool(expected.intersection(ids[:5]))),
        'passage_mrr': 1 / rank if rank else 0,
        'top_1_useful_precision': int(bool(ids and ids[0] in useful)),
        'top_3_useful_precision': sum(pid in useful for pid in ids[:3]) / 3,
        'distractor_at_3': sum(pid in distractors for pid in ids[:3]),
    }


def evaluate(data, ranker=rank_passages):
    validate(data)
    passages = data['passages']
    lookup = {p['passage_id']: p for p in passages}
    details, scored = [], []
    for case in data['cases']:
        # Shared corpus, unchanged production defaults: two per document, dedup on.
        hits = ranker(passages, case['question'], limit=len(passages))
        ids = [p['passage_id'] for p in hits]
        labels = {pid: label for field, label in zip(LABELS, ('answer-bearing', 'acceptable', 'distractor'))
                  for pid in case[field]}
        metrics = None if case['status'] == 'AMBIGUOUS' else measure(case, hits, passages)
        if metrics is not None:
            scored.append(metrics)
        details.append({
            'id': case['id'], 'language': case['language'], 'question': case['question'],
            'status': case['status'], 'failure_category': case['failure_category'],
            'rationale': case['rationale'], 'metrics': metrics,
            'needs_attention': metrics is not None and (metrics['passage_mrr'] != 1
                or metrics['top_1_useful_precision'] != 1 or metrics['distractor_at_3'] > 0),
            'expected': [{'passage_id': pid, 'text': lookup[pid]['passage'],
                          'rank': ids.index(pid) + 1 if pid in ids else None}
                         for pid in case['expected_passage_ids']],
            'top_results': [{'rank': i, 'passage_id': p['passage_id'], 'text': p['passage'],
                             'label': labels.get(p['passage_id'], 'unlabeled')}
                            for i, p in enumerate(hits[:5], 1)],
        })
    names = ('document_hit_at_5', 'passage_hit_at_5', 'passage_mrr',
             'top_1_useful_precision', 'top_3_useful_precision', 'distractor_at_3')
    metrics = {k: sum(m[k] for m in scored) / len(scored) if scored else None for k in names}
    metrics['distractor_slot_rate_at_3'] = metrics['distractor_at_3'] / 3 if scored else None
    return {'count': len(details), 'scored_count': len(scored), 'ambiguous_count': len(details)-len(scored),
            'languages': dict(Counter(c['language'] for c in data['cases'])),
            'categories': dict(Counter(c['failure_category'] for c in data['cases'])),
            'metrics': metrics, 'cases': details}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark', type=Path, default=DEFAULT,
                        help='Optional external private fixture; only aggregate metrics are printed.')
    args = parser.parse_args(argv)
    try:
        data, digest = load_benchmark(args.benchmark)
        report = evaluate(data)
        if args.benchmark.resolve() == DEFAULT.resolve():
            report['fixture_sha256'] = digest
        else:
            # External fixtures may contain private questions, paths or source metadata.
            report = {k: report[k] for k in ('count', 'scored_count', 'ambiguous_count', 'metrics')}
        print(json.dumps(report, ensure_ascii=True, indent=2))
        return 0
    except BenchmarkError as exc:
        print(json.dumps({'error': str(exc)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

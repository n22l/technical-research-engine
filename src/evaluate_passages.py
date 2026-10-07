"""Synthetic regression metrics; not factual accuracy or held-out validation."""
import json
import argparse
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import patch
from passage_ranking import rank_passages
from research_search import keyword_scores


CASES = [
    ('combination', 'reusable booster reflight', 'The reusable booster completed reflight.', ['reusable', 'booster', 'reflight']),
    ('phrase', '"routine operational reuse"', 'The test examined routine operational reuse.', ['routine', 'operational', 'reuse']),
    ('technical', 'Zhuque-3 model 2026', 'Zhuque-3 model 2026 completed a fictional test.', ['zhuque-3', '2026']),
    ('alias', 'booster re-flight', 'The booster completed reflight.', ['booster', 'reflight']),
    ('chinese', '一级重复使用', '该试验验证一级重复使用。', ['一级', '重复使用']),
    ('mixed', '朱雀三号 reflight', '朱雀三号 reflight 是本段的测试主题。', ['朱雀三号', 'reflight']),
    ('pdf', 'engine inspection record', 'The engine inspection record is in this PDF paragraph.', ['engine', 'inspection', 'record']),
]


def fixture(case):
    name, query, sentence, important = case
    rows = []
    # Six title-only distractors ensure Hit@5 can expose page-ranking failures.
    for i in range(6):
        rows.append({'passage_id': f'{name}-d{i}:p1', 'passage': 'General visitor information and unrelated activities.',
                     'source': {'id': f'{name}-d{i}', 'title': query}, 'location': {}})
    rows.append({'passage_id': f'{name}-expected:p1', 'passage': sentence,
                 'source': {'id': f'{name}-expected', 'title': 'Technical record'},
                 'location': {'paragraph_index': 1, 'page_number': 3 if name == 'pdf' else None}})
    return rows


def evaluate(scorer=keyword_scores):
    reports = {}
    for mode in ['before', 'after']:
        metrics = {'document_hit_at_5': 0, 'passage_hit_at_5': 0, 'passage_mrr': 0, 'sentence_hit_at_1': 0}
        details = []
        for case in CASES:
            name, query, sentence, important = case
            rows = fixture(case); expected = f'{name}-expected:p1'
            if mode == 'before':
                scores = scorer([p['passage'] for p in rows], query, [p['source']['title'] for p in rows])
                docs = [p['source']['id'] for s, p in sorted(zip(scores, rows), key=lambda x:-x[0]) if s > 0]
                ps = scorer([p['passage'] for p in rows], query)
                hits = [p for s, p in sorted(zip(ps, rows), key=lambda x:-x[0]) if s > 0]
            else:
                hits = rank_passages(rows, query, 20)
                docs = list(dict.fromkeys(p['source']['id'] for p in hits))
            ids = [p['passage_id'] for p in hits]
            metrics['document_hit_at_5'] += f'{name}-expected' in docs[:5]
            metrics['passage_hit_at_5'] += expected in ids[:5]
            metrics['passage_mrr'] += 1/(ids.index(expected)+1) if expected in ids else 0
            best = hits[0].get('retrieval_match', {}).get('best_sentence', {}).get('text') if hits else None
            metrics['sentence_hit_at_1'] += best == sentence
            details.append({'id': name, 'query': query, 'expected_document': f'{name}-expected',
                'expected_passage': expected, 'expected_sentence': sentence, 'important_terms': important,
                'documents': docs[:5], 'passages': ids[:5]})
        reports[mode] = {k: v/len(CASES) for k,v in metrics.items()}
        if mode == 'before': reports[mode]['sentence_hit_at_1'] = None
        reports[mode]['cases'] = details
    return {'note': 'Synthetic development fixture; no factual verdict evaluation.', 'count':len(CASES), **reports}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', help='Trusted local Git revision for the historical ranker')
    args = parser.parse_args()
    scorer = keyword_scores
    if args.baseline_ref:
        # Execute only the explicitly selected local repository revision, never downloaded text.
        modules = {}
        for name in ('research_search', 'retrieval_constraints'):
            module = types.ModuleType(name)
            module.__file__ = str(Path(__file__).with_name(name+'.py'))
            code = subprocess.run(['git','show',args.baseline_ref+':src/'+name+'.py'],
                capture_output=True,text=True,encoding='utf-8',check=True).stdout
            exec(compile(code,module.__file__,'exec'),module.__dict__)
            modules[name] = module
        def scorer(*a, **kw):
            with patch.dict(sys.modules, {'retrieval_constraints':modules['retrieval_constraints']}):
                return modules['research_search'].keyword_scores(*a, **kw)
    report = evaluate(scorer)
    report['baseline'] = args.baseline_ref or 'current lexical ablation; not historical baseline'
    print(json.dumps(report, ensure_ascii=True, indent=2))

"""Offline frozen retrieval regression, not a held-out factual accuracy score."""
import json
import hashlib
from pathlib import Path
from research_search import keyword_scores


def evaluate(path=None):
    path = path or Path(__file__).resolve().parents[1] / 'data/evaluation/retrieval-v1.json'
    raw = path.read_bytes().replace(b'\r\n', b'\n')
    fingerprint = hashlib.sha256(raw).hexdigest()
    expected_hash = path.with_suffix('.sha256').read_text().strip()
    if fingerprint != expected_hash:
        raise ValueError('Frozen corpus changed: create a new version and review labels before updating its hash.')
    data = json.loads(raw.decode('utf-8'))
    passages = data['passages']
    result = {'version': data['version'], 'sha256': fingerprint, 'review_method': data['review_method'], 'modes': {}}
    for name, constrained in [('lexical_ablation', False), ('subject_constrained', True)]:
        rows = []
        for case in data['questions']:
            scores = keyword_scores([p['passage'] for p in passages], case['question'], require_subject=constrained)
            ranked = sorted([(s, p['passage_id']) for s, p in zip(scores, passages) if s > 0], reverse=True)[:5]
            ids = [pid for _, pid in ranked]
            rows.append({'id': case['id'], 'retrieved': ids, 'expected': case['expected'],
                         'passed': bool(set(ids) & set(case['expected'])) if case['expected'] else not ids})
        result['modes'][name] = {'passed': sum(r['passed'] for r in rows), 'total': len(rows), 'cases': rows}
    return result


if __name__ == '__main__':
    print(json.dumps(evaluate(), ensure_ascii=False, indent=2))

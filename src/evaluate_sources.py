"""Opt-in seeded live acquisition; repeatable offline evaluation of private snapshots.

No network by default. Full source paragraphs/captures remain in the external folder.
This measures a small known-source development set, not general discovery recall.
"""
import argparse
import json
from pathlib import Path
from research_search import ROOT, external_directory
from local_search import LocalSearchProvider
from web_sources import SourcePolicy
from passage_ranking import rank_passages
from retrieval_constraints import coverage
from verification_models import digest


def evaluate(provider, cases):
    rows = []
    entries = provider.entries or []
    for case in cases:
        hits = provider.search(case['query'], limit=5)
        documents = [e for e in entries if e['url'] in {h.url for h in hits}]
        passages = [dict(p, source=dict(p['source'], title=e['title']))
                    for e in documents for p in e.get('passages', [])]
        ranked = rank_passages(passages, case['query'], limit=5)
        if case.get('expect_empty'):
            passed = not hits and not ranked
            status = 'EXPECTED_MISSING_COVERAGE' if passed else 'WRONG_SUBJECT'
        else:
            found = [p for p in ranked if p['source']['source_url'] == case['url']
                     and case['anchor'].lower() in p['passage'].lower()
                     and digest(p['passage']) == case['expected_passage_hash']]
            passed = bool(found)
            status = 'EXPECTED_PASSAGE_FOUND' if passed else coverage(case['query'],
                [p['passage'] for e in entries for p in e.get('passages', [])])['status']
        rows.append(dict(id=case['id'], passed=passed, status=status,
            urls=[h.url for h in hits], passage_ids=[p['passage_id'] for p in ranked],
            passage_hashes=[digest(p['passage']) for p in ranked]))
    return dict(passed=sum(r['passed'] for r in rows), total=len(rows), cases=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', required=True, help='Separate existing external evaluation directory')
    parser.add_argument('--refresh', action='store_true', help='Explicit bounded public network acquisition')
    args = parser.parse_args()
    base = external_directory(args.data_dir)
    fixture = ROOT/'data/evaluation/source-cases-v1.json'
    if digest(fixture.read_bytes().replace(b'\r\n', b'\n')) != fixture.with_suffix('.sha256').read_text().strip():
        raise ValueError('Frozen evaluation set changed; explicitly review and version it')
    cases = json.loads(fixture.read_text(encoding='utf-8'))['cases']
    urls = sorted({c['url'] for c in cases if 'url' in c})
    approved = SourcePolicy.load(ROOT/'config/source-policy.json')
    from urllib.parse import urlsplit
    rules = {}
    for url in urls:
        rule = approved.qualify(url)
        if not rule['allowed']: raise ValueError('Evaluation source is not approved')
        host = urlsplit(url).hostname
        rules.setdefault(host, dict(rule, crawl_hosts=[], crawl_seeds=[], sitemaps=[], feeds=[]))['crawl_seeds'].append(url)
    provider = LocalSearchProvider(base, SourcePolicy(rules), max_pages=10, max_depth=0,
                                   per_host=3, max_sitemap_files=1, max_seconds=90)
    provider._load()
    if args.refresh:
        provider.refresh = True
        provider._crawl()
    elif provider.entries is None:
        parser.error('No frozen snapshot. Run once with --refresh to acquire sources.')
    report = evaluate(provider, cases)
    report['scope'] = 'Seeded known-source development check; not whole-site discovery or a verdict'
    report['source_hashes'] = {e['url']:e.get('source',{}).get('content_hash') for e in provider.entries}
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report['passed'] == report['total'] else 1


if __name__ == '__main__': raise SystemExit(main())

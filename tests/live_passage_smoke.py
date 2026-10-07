"""Opt-in bounded public NASA fetches; full evidence goes only to private storage."""
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from urllib.robotparser import RobotFileParser
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from research_search import private_directory, ROOT
from web_sources import SourcePolicy, Fetcher, parse_document
from passage_ranking import rank_passages
from verification_models import now

CASES = [
    ('phrase/subdomain', '"halo orbit"', 'https://science.nasa.gov/asset/webb/webbs-orbit-at-sun-earth-lagrange-point-2-l2/'),
    ('combination/deep', 'Webb Sun Earth L2', 'https://science.nasa.gov/blogs/webb/2022/01/21/webbs-journey-to-l2-is-nearly-complete/'),
    ('PDF', 'primary mirror size', 'https://science.nasa.gov/wp-content/uploads/2024/08/webbfactsheet.pdf'),
]

def main():
    base = private_directory()
    policy = SourcePolicy.load(ROOT/'config/source-policy.json')
    fetcher = Fetcher(policy)
    raw, media = fetcher.fetch('https://science.nasa.gov/robots.txt')
    if media != 'text/plain': raise ValueError('Robots unavailable')
    robots = RobotFileParser(); robots.parse(raw.decode('utf-8').splitlines())
    delay = max(1, robots.crawl_delay('TechnicalResearchEngine') or 1)
    rate = robots.request_rate('TechnicalResearchEngine')
    if rate and rate.requests: delay = max(delay, rate.seconds/rate.requests)
    if delay > 10: raise ValueError('Robots delay exceeds smoke budget')
    rows = []
    for kind, query, url in CASES:
        row = dict(kind=kind, query=query, url=url, checked_at=now())
        if not robots.can_fetch('TechnicalResearchEngine',url): row['status']='ROBOTS_BLOCKED'
        else:
            try:
                time.sleep(delay)
                body, media = fetcher.fetch(url)
                doc = parse_document(url,body,media,policy)
                hits = rank_passages(doc.passages,query,1)
                row.update(status='MATCH_FOUND' if hits else 'NO_MATCH',publisher=doc.source.publisher,
                           source_hash=doc.source.content_hash, matches=[dict(h,location=asdict(h['location'])) for h in hits])
            except Exception as exc: row['status']=type(exc).__name__
        rows.append(row)
    from verify import private_output
    private_output(base,{'smoke_tests':rows})
    print(json.dumps([{k:v for k,v in r.items() if k!='matches'} for r in rows],indent=2))

if __name__ == '__main__': main()

"""CLI for bounded source research and human-reviewed verification."""
import sys
sys.dont_write_bytecode = True
import contextlib
import io
from dataclasses import asdict
import json
import os
from pathlib import Path
import time
import uuid
from research_search import private_directory, private_output, safe_file, Parser, SafeError, external_directory
from verification_models import ResearchRequest, digest, now
from web_sources import SourcePolicy, Fetcher, parse_document
from verification import decompose, candidates, assess, markdown
from search_discovery import configured_provider, discover, SearchError

ROOT = Path(__file__).resolve().parents[1]


def demo(review_only=False):
    """Invented evidence, never a factual claim about an actual space program."""
    policy = SourcePolicy({'agency.example': {'allowed': True, 'tier': 1, 'type': 'government',
                                              'publisher': 'Fictional test agency'}})
    request = ResearchRequest('Test booster has demonstrated routine operational reuse.',
                              requested_as_of_date='2026-06-01', domain='aerospace')
    body = b'''<html lang="en"><title>Synthetic booster test record</title>
    <meta property="article:published_time" content="2026-05-01">
    <h2>Test results</h2><p>The test booster landed. No reflight has occurred,
    and routine operational reuse has not been demonstrated.</p></html>'''
    docs = [parse_document('https://agency.example/record', body, 'text/html', policy)]
    claims = decompose(request)
    evidence = candidates(claims, docs)
    reviews = {e.evidence_id: {'claim_id': e.claim_id, 'document_hash': docs[0].source.content_hash,
        'reviewer': 'synthetic fixture author', 'rationale': 'The invented record explicitly denies the material capability.',
        'stance': 'CONTRADICTS', 'strength': 'DIRECT', 'basis': 'observation', 'relevant': True,
        'material_scope_matches': True, 'status': 'TESTING', 'milestone': 'landing'} for e in evidence}
    result = assess(request, claims, docs, evidence, reviews, review_only=review_only)
    result['research_scope'] = 'synthetic offline development fixture; no live search'
    return result


def research(request, policy, urls, base, offline=False, captures=None, reviews=None,
             explicit_claims=None, max_sources=8, max_queries=8, review_only=False,
             search_provider=None, results_per_query=5, max_candidate_urls=20,
             automatic=False, configuration_error=None):
    base = external_directory(base)
    if not 1 <= max_sources <= 20 or not 1 <= max_queries <= 40:
        raise ValueError('Research limits are out of range')
    claims = decompose(request, explicit_claims)
    documents, failures, events, retrieved = [], [], [], []
    discovery = discover(claims, policy, urls, search_provider, domain=request.domain,
                         offline=offline, max_queries=max_queries, max_sources=max_sources,
                         results_per_query=results_per_query, max_candidates=max_candidate_urls)
    if configuration_error and not offline:
        discovery['failures'] = [configuration_error]
    failures.extend(discovery['failures'])
    if any(c['source_policy_status'] != 'APPROVED_EVIDENCE_SOURCE'
           and any(d['provider'] == 'manual_urls' for d in c['discoveries'])
           for c in discovery['candidates']):
        failures.append('SOURCE_NOT_ALLOWED')
    urls = discovery['selected_urls']
    for url in urls:
        try:
            if not policy.qualify(url)['allowed']:
                failures.append('SOURCE_NOT_ALLOWED')
                continue
            if offline:
                capture = (captures or {}).get(url)
                if not capture:
                    failures.append('FETCH_FAILED')
                    continue
                capture_path = safe_file(base, capture['file'])
                if capture_path.stat().st_size > 4_000_000:
                    raise ValueError('Oversized capture')
                body = capture_path.read_bytes()
                media = capture['media_type']
                events.append({'stage': 'fetch', 'status': 'ok', 'url': url, 'mode': 'offline'})
            else:
                body, media = Fetcher(policy).fetch(url)
                # Exclusive files under validated external root: no user filenames.
                name = 'capture-' + uuid.uuid4().hex + '.bin'
                fd = os.open(base / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(body)
                retrieved.append({'url': url, 'file': name, 'content_hash': digest(body),
                                  'retrieved_at': now(), 'media_type': media})
                events.append({'stage': 'fetch', 'status': 'ok', 'url': url})
            try:
                # Third-party parsers may print fragments from malformed inputs.
                # Keep those diagnostics out of production terminal output.
                with contextlib.redirect_stderr(io.StringIO()):
                    doc = parse_document(url, body, media, policy)
            except Exception:
                failures.append('PARSE_FAILED')
                events.append({'stage': 'parse', 'status': 'failed', 'url': url})
                continue
            documents.append(doc)
            events.append({'stage': 'parse', 'status': 'ok', 'url': url, 'document_hash': doc.source.content_hash})
        except Exception:
            failures.append('FETCH_FAILED')
            events.append({'stage': 'fetch', 'status': 'failed', 'url': url})
        finally:
            if not offline:
                time.sleep(.25)
    evidence = candidates(claims, documents)
    result = assess(request, claims, documents, evidence, reviews, failures, review_only)
    # A failed automatic search is a process failure, never a factual verdict.
    # Legacy manual/local assessment retains its existing, explicitly limited scope.
    automatic = automatic or search_provider is not None
    if automatic and not offline and discovery['status'] != 'SEARCH_COMPLETE':
        result.update(verdict=None, assessments=[], short_answer='Current web discovery failed; candidate evidence requires review.')
        result['failures'] = [f for f in result['failures'] if f != 'INSUFFICIENT_EVIDENCE']
    scope = ('supplied local captures only' if offline else
             'automatic web discovery plus supplied URLs; human review required' if automatic else
             'manual public URLs only; current web search unavailable')
    result.update(research_scope=scope, search=discovery,
                  run_manifest={'engine_version': '0.3', 'request': asdict(request), 'documents': [asdict(d.source) for d in documents],
                                'search': discovery, 'source_dependencies': result['source_differences']['likely_dependencies'],
                                'captures': retrieved, 'evidence_ids': [e.evidence_id for e in evidence],
                                'configuration': {'offline': offline, 'max_sources': max_sources, 'max_queries': max_queries,
                                                  'results_per_query': results_per_query, 'max_candidate_urls': max_candidate_urls,
                                                  'source_policy': policy.rules}, 'events': events})
    return result


def main(argv=None):
    try:
        parser = Parser(description=__doc__)
        parser.add_argument('command', choices=['verify', 'research'])
        parser.add_argument('text', nargs='?')
        parser.add_argument('--demo', action='store_true')
        parser.add_argument('--offline', action='store_true')
        parser.add_argument('--review-only', action='store_true')
        parser.add_argument('--as-of')
        parser.add_argument('--domain', choices=['aerospace'])
        parser.add_argument('--language', default='en')
        parser.add_argument('--request-type', default='AUTO', choices=['AUTO','CLAIM','QUESTION','COMPARISON'])
        parser.add_argument('--output', default='json', choices=['json','markdown'])
        parser.add_argument('--bundle', help='JSON filename relative to external private directory')
        parser.add_argument('--question-file', help='UTF-8 filename relative to external private directory')
        parser.add_argument('--url', action='append', default=[], help='Manual public source URL; repeatable')
        parser.add_argument('--search-provider', choices=['local', 'manual', 'brave'])
        parser.add_argument('--max-crawl-pages', type=int, default=12)
        parser.add_argument('--refresh-local-index', action='store_true')
        parser.add_argument('--policy', help='Policy filename relative to external private directory')
        parser.add_argument('--max-sources', type=int, default=8)
        parser.add_argument('--max-queries', type=int, default=8)
        parser.add_argument('--results-per-query', type=int, default=5)
        parser.add_argument('--max-candidate-urls', type=int, default=20)
        args = parser.parse_args(argv)
        if args.demo:
            if args.text or args.bundle or args.policy or args.question_file or args.url or args.search_provider:
                raise SafeError('Demo cannot read production input.')
            result = demo(review_only=args.review_only or args.command == 'research')
            print(markdown(result) if args.output == 'markdown' else json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        base = private_directory()
        bundle = json.loads(safe_file(base, args.bundle).read_text(encoding='utf-8')) if args.bundle else {}
        if args.question_file and args.text:
            raise SafeError('Use either request text or --question-file.')
        text = args.text or bundle.get('text', '')
        if args.question_file:
            question_path = safe_file(base, args.question_file)
            if question_path.stat().st_size > 40000:
                raise SafeError('Question file exceeds size limit.')
            text = question_path.read_text(encoding='utf-8')
        if not 1 <= args.max_sources <= 20 or not 1 <= args.max_queries <= 40:
            raise SafeError('Research limits are out of range.')
        request = ResearchRequest(text, args.request_type,
                                  **({'requested_as_of_date': args.as_of} if args.as_of else {}),
                                  language=args.language, domain=args.domain)
        policy = SourcePolicy.load(safe_file(base, args.policy) if args.policy else ROOT / 'config/source-policy.json')
        provider, configuration_error = None, None
        # Preserve existing bundle/manual URL behavior unless a provider is selected.
        default_provider = 'manual' if args.bundle or args.url else 'local'
        provider_name = args.search_provider or os.environ.get('TECH_RESEARCH_SEARCH_PROVIDER', default_provider)
        if not args.offline:
            try:
                provider = configured_provider(provider_name, base=base, policy=policy,
                                               max_pages=args.max_crawl_pages, refresh=args.refresh_local_index)
            except SearchError as exc:
                configuration_error = exc.code
        urls = bundle.get('urls', []) + args.url
        automatic = provider_name != 'manual' or not urls
        result = research(request, policy, urls, base, args.offline,
                          bundle.get('captures'), bundle.get('reviews'), bundle.get('atomic_claims'),
                          args.max_sources, args.max_queries, args.review_only or args.command == 'research',
                          provider, args.results_per_query, args.max_candidate_urls, automatic, configuration_error)
        result['search']['requested_provider'] = provider_name
        # Exact evidence and full provenance stay private. Never stdout production.
        if args.output == 'markdown':
            result['markdown_report'] = markdown(result)
        private_output(base, result)
        print(f"Search queries issued: {len(result['search']['queries_issued'])}; "
              f"candidate URLs: {len(result['search']['candidates'])}; "
              f"selected: {len(result['search']['selected_urls'])}; "
              f"parsed: {len(result['sources'])}; evidence passages: {len(result['key_evidence'])}.")
        if result['search']['failures']:
            print('Search status: ' + ', '.join(result['search']['failures']) +
                  '. Manual URLs and offline captures remain available.')
        print('Private verification report saved as result-*.json in the configured external directory.')
        return 0
    except SafeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        print('Verification failed. Check private configuration and input schemas locally.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())

"""Bounded discovery only. Search titles/snippets never enter document evidence."""
from dataclasses import dataclass
import http.client
import ipaddress
import json
import os
import re
import time
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit, urlencode, unquote_plus

from verification_models import now
from web_sources import public_url


SEARCH_ERRORS = {'SEARCH_UNAVAILABLE', 'SEARCH_AUTH_FAILED', 'SEARCH_RATE_LIMITED',
                 'SEARCH_PROVIDER_ERROR', 'SEARCH_NO_RESULTS'}


class SearchError(Exception):
    def __init__(self, code):
        self.code = code if code in SEARCH_ERRORS else 'SEARCH_PROVIDER_ERROR'
        super().__init__(self.code)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    provider: str
    rank: int
    discovered_at: str


class SearchProvider(Protocol):
    name: str
    def search(self, query: str, *, limit: int) -> list[SearchResult]: ...


class ManualURLProvider:
    name = 'manual_urls'

    def __init__(self, urls):
        self.urls = list(dict.fromkeys(urls))

    def search(self, query, *, limit=20):
        return [SearchResult('', u, '', self.name, i, now())
                for i, u in enumerate(self.urls[:limit], 1)]


class BraveSearchProvider:
    """Documented Web Search API; fixed endpoint, no redirects/retries/proxies."""
    name = 'brave'

    def __init__(self, api_key, timeout=15):
        if not api_key:
            raise SearchError('SEARCH_UNAVAILABLE')
        self._api_key = api_key
        self.timeout = timeout
        self._last_call = None

    def search(self, query, *, limit=5):
        if not isinstance(query, str) or not query.strip() or len(query) > 600 or len(query.split()) > 75:
            raise SearchError('SEARCH_PROVIDER_ERROR')
        if not 1 <= limit <= 20:
            raise SearchError('SEARCH_PROVIDER_ERROR')
        # At most one request per second. A 429 stops discovery; no retries.
        if self._last_call is not None:
            time.sleep(max(0, 1 - (time.monotonic() - self._last_call)))
        self._last_call = time.monotonic()
        conn = http.client.HTTPSConnection('api.search.brave.com', timeout=self.timeout)
        try:
            path = '/res/v1/web/search?' + urlencode({'q': query, 'count': limit,
                'result_filter': 'web', 'text_decorations': 'false', 'spellcheck': 'false'})
            conn.request('GET', path, headers={'X-Subscription-Token': self._api_key,
                'Accept': 'application/json', 'Accept-Encoding': 'identity', 'Cache-Control': 'no-cache'})
            response = conn.getresponse()
            if response.status in (401, 403):
                raise SearchError('SEARCH_AUTH_FAILED')
            if response.status == 429:
                raise SearchError('SEARCH_RATE_LIMITED')
            if (response.status != 200 or response.getheader('Content-Encoding', 'identity') != 'identity'
                    or int(response.getheader('Content-Length', '0')) > 2_000_000):
                raise SearchError('SEARCH_PROVIDER_ERROR')
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise SearchError('SEARCH_PROVIDER_ERROR')
            if self._api_key.encode() in raw:
                raise SearchError('SEARCH_PROVIDER_ERROR')
            payload = json.loads(raw)
            if not isinstance(payload, dict) or payload.get('type') != 'search':
                raise SearchError('SEARCH_PROVIDER_ERROR')
            web = payload.get('web')
            if web is None:
                web = {}
            rows = web.get('results', []) if isinstance(web, dict) else None
            if not isinstance(rows, list):
                raise SearchError('SEARCH_PROVIDER_ERROR')
            results = []
            for rank, row in enumerate(rows[:limit], 1):
                if not isinstance(row, dict):
                    raise SearchError('SEARCH_PROVIDER_ERROR')
                fields = [row.get('title', ''), row.get('url'), row.get('description', '')]
                if any(not isinstance(v, str) or len(v) > bound
                       for v, bound in zip(fields, (2000, 4096, 10000))):
                    raise SearchError('SEARCH_PROVIDER_ERROR')
                results.append(SearchResult(fields[0], fields[1], fields[2], self.name, rank, now()))
            return results
        except SearchError:
            raise
        except Exception:
            # Never expose response bodies, URLs containing keys, or raw exceptions.
            raise SearchError('SEARCH_PROVIDER_ERROR') from None
        finally:
            conn.close()


def configured_provider(name=None, *, base=None, policy=None, max_pages=12, refresh=False):
    name = name if name is not None else os.environ.get('TECH_RESEARCH_SEARCH_PROVIDER', 'local')
    if name == 'local':
        if base is None or policy is None:
            raise SearchError('SEARCH_UNAVAILABLE')
        from local_search import LocalSearchProvider
        return LocalSearchProvider(base, policy, max_pages, refresh)
    if name == 'manual':
        return None
    if name == 'brave':
        return BraveSearchProvider(os.environ.get('BRAVE_SEARCH_API_KEY'))
    raise SearchError('SEARCH_UNAVAILABLE')


def normalize_url(url):
    if not isinstance(url, str) or len(url) > 4096 or '\\' in url:
        raise ValueError('Invalid URL')
    p = public_url(url)
    host = p.hostname.lower()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if ('.' not in host or host.endswith(('.localhost', '.local', '.internal', '.lan'))
                or not re.fullmatch(r'[a-z0-9.-]+', host)):
            raise ValueError('Nonpublic hostname')
    else:
        if not address.is_global:
            raise ValueError('Nonpublic address')
    # Preserve order, duplicates and encoding of meaningful query parameters.
    query = '&'.join(part for part in p.query.split('&') if part and not (
        unquote_plus(part.split('=', 1)[0]).lower().startswith('utm_') or
        unquote_plus(part.split('=', 1)[0]).lower() in {'gclid', 'fbclid', 'msclkid'}))
    authority = '[' + host + ']' if ':' in host else host
    return urlunsplit(('https', authority, p.path or '/', query, ''))


def query_intents(claim, domain=None, policy=None):
    # Leave room for deterministic modifiers within the provider query limits.
    text = ' '.join(claim.text.split()[:55])[:420]
    hint = ''
    if domain == 'aerospace':
        from domains.aerospace.search_hints import search_hint
        hint = search_hint(claim.text)
    primary = next((h for h, r in (policy.rules.items() if policy else [])
                    if r.get('allowed') and r.get('primary') and r.get('publisher')
                    and r['publisher'].casefold() in claim.text.casefold()), None)
    suffixes = [('PRIMARY_SOURCE', ' official technical report' + hint),
                ('OFFICIAL_RECORD', ' site:' + primary if primary else ' official government record'),
                ('INDEPENDENT_CONFIRMATION', ' independent reporting confirmation'),
                ('LATEST_UPDATE', ' latest update revised'),
                ('CONTRADICTION_OR_CORRECTION', ' correction denied failed delayed not yet')]
    return [{'claim_id': claim.claim_id, 'intent': label, 'query': (text + suffix)[:600]}
            for label, suffix in suffixes]


def discover(claims, policy, manual_urls, provider=None, *, domain=None, offline=False,
             max_queries=8, results_per_query=5, max_candidates=20, max_sources=8):
    if not (1 <= max_queries <= 40 and 1 <= results_per_query <= 20
            and 1 <= max_candidates <= 100 and 1 <= max_sources <= 20):
        raise ValueError('Research limits are out of range')
    if not isinstance(manual_urls, list) or len(manual_urls) > 100:
        raise ValueError('Invalid manual URL list')
    per_claim = [query_intents(c, domain, policy) for c in claims]
    # Round-robin avoids spending the full query budget on the first subclaim.
    intents = [items[i] for i in range(5) for items in per_claim][:max_queries]
    report = {'provider': provider.name if provider and not offline else 'manual_urls',
              'search_time': now(), 'planned_queries': intents, 'queries_issued': [],
              'results_returned': 0, 'candidates': [], 'selected_urls': [], 'rejected_urls': [],
              'failures': [], 'status': 'OFFLINE' if offline else 'CURRENT_WEB_RESEARCH_UNAVAILABLE',
              'configuration': {'max_queries': max_queries, 'results_per_query': results_per_query,
                                'max_candidate_urls': max_candidates, 'max_sources': max_sources},
              'candidate_limit_reached': False}
    by_url = {}

    def add(result, intent):
        if (not isinstance(result, SearchResult) or not isinstance(result.title, str)
                or not isinstance(result.snippet, str) or len(result.title) > 2000
                or len(result.snippet) > 10000 or type(result.rank) is not int or result.rank < 1
                or not isinstance(result.provider, str) or len(result.provider) > 100
                or not isinstance(result.discovered_at, str) or len(result.discovered_at) > 100):
            raise SearchError('SEARCH_PROVIDER_ERROR')
        try:
            url = normalize_url(result.url)
            rule = policy.qualify(url)
            status = ('APPROVED_EVIDENCE_SOURCE' if rule['allowed'] else
                      'UNKNOWN' if not rule.get('registered', True) else
                      'DISCOVERY_ONLY' if rule.get('type') == 'discovery_only' else 'REJECTED')
        except (ValueError, TypeError):
            url, rule, status = None, {}, 'REJECTED'
        key = url or str(result.url)[:4096]
        occurrence = {'original_url': str(result.url)[:4096], 'query_intent': intent,
                      'provider_rank': result.rank, 'provider': result.provider,
                      'discovered_at': result.discovered_at}
        if key in by_url:
            by_url[key]['discoveries'].append(occurrence)
            return
        if len(by_url) >= max_candidates:
            report['candidate_limit_reached'] = True
            return
        # Manual capture/review IDs must keep their original URL identity.
        fetch_url = result.url if url and result.provider == 'manual_urls' else url
        candidate = {'url': fetch_url, 'normalized_url': url, 'title': result.title, 'snippet': result.snippet,
                     'provider_rank': result.rank, 'query_intent': intent,
                     'source_policy_status': status, 'source_tier': rule.get('tier'),
                     'primary': bool(rule.get('primary')), 'publisher': rule.get('publisher'),
                     'reason_selected': None, 'discoveries': [occurrence],
                     'policy_note': 'UNREGISTERED_SOURCE' if status == 'UNKNOWN' else status}
        by_url[key] = candidate

    for result in ManualURLProvider(manual_urls).search('', limit=100):
        add(result, {'intent': 'MANUAL_URL', 'claim_id': None})
    if provider and not offline:
        report['status'] = 'SEARCH_COMPLETE'
        for intent in intents:
            issued = dict(intent, issued_at=now(), status='STARTED', result_count=0)
            report['queries_issued'].append(issued)
            try:
                results = provider.search(intent['query'], limit=results_per_query)
                if not isinstance(results, list):
                    raise SearchError('SEARCH_PROVIDER_ERROR')
                for result in results[:results_per_query]:
                    add(result, intent)
                issued.update(status='OK', result_count=min(len(results), results_per_query))
                report['results_returned'] += issued['result_count']
            except Exception as exc:
                code = exc.code if isinstance(exc, SearchError) else 'SEARCH_PROVIDER_ERROR'
                issued['status'] = code
                report['failures'].append(code)
                report['status'] = 'SEARCH_FAILED'
                break  # Avoid repeated authentication failures or API charges.
        if report['status'] == 'SEARCH_COMPLETE' and not report['results_returned']:
            report['failures'].append('SEARCH_NO_RESULTS')
    elif not offline:
        report['failures'].append('SEARCH_UNAVAILABLE')
    report['candidates'] = list(by_url.values())
    if provider and hasattr(provider, 'audit'):
        report['local_index'] = provider.audit
    eligible = [c for c in by_url.values() if c['source_policy_status'] == 'APPROVED_EVIDENCE_SOURCE']
    # Prefer tier/primary status, then diversify publishers before taking repeats.
    eligible.sort(key=lambda c: (c['source_tier'] or 99, not c['primary'], c['provider_rank']))
    selected, used = [], set()
    for c in eligible:
        publisher = c['publisher'] or urlsplit(c['url']).hostname
        if publisher not in used and len(selected) < max_sources:
            selected.append(c)
            used.add(publisher)
    for c in eligible:
        if c not in selected and len(selected) < max_sources:
            selected.append(c)
    for c in selected:
        c['reason_selected'] = 'approved policy; tier/primary preference with publisher diversity; not evidence strength'
    report['selected_urls'] = [c['url'] for c in selected]
    report['rejected_urls'] = [{'url': c['url'] or c['discoveries'][0]['original_url'],
                               'reason': c['policy_note'] if c not in eligible else 'FETCH_BUDGET'}
                              for c in by_url.values() if c not in selected]
    return report


def evaluate_discovery(selected_urls, expected_authoritative_domains, forbidden_domains, k=8):
    """Fixture domain coverage only; no claim of production search accuracy."""
    hosts = [urlsplit(u).hostname for u in selected_urls[:k]]
    expected, forbidden = set(expected_authoritative_domains), set(forbidden_domains)
    return {'authoritative_domain_recall_at_k': len(set(hosts) & expected) / len(expected) if expected else None,
            'labeled_approved_precision_at_k': sum(h in expected and h not in forbidden for h in hosts) / len(hosts) if hosts else None,
            'forbidden_selected': sorted(set(hosts) & forbidden)}

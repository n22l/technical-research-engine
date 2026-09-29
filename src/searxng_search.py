"""Optional SearXNG JSON discovery API; instance selection is explicit."""
import json
import time
from urllib.parse import urlsplit, urlencode

from search_discovery import SearchResult, SearchError, normalize_url
from verification_models import now
from web_sources import SourcePolicy, Fetcher, FetchError


class SearXNGProvider:
    name = 'searxng'

    def __init__(self, instance_url):
        if not instance_url:
            raise SearchError('SEARCH_UNAVAILABLE')
        try:
            parsed = urlsplit(instance_url)
            if parsed.query or parsed.fragment:
                raise ValueError('Instance URL must not have query or fragment')
            self.instance_url = normalize_url(instance_url).rstrip('/')
        except (TypeError, ValueError):
            raise SearchError('SEARCH_UNAVAILABLE') from None
        # This transport policy allows querying only the configured instance.
        # It is never merged into the evidence source-policy registry.
        policy = SourcePolicy({urlsplit(self.instance_url).hostname: {'allowed': True}})
        self.fetcher = Fetcher(policy, max_bytes=2_000_000, timeout=15, accept='application/json')
        self._last_call = None
        self.audit = {'endpoint': self.instance_url + '/search', 'unresponsive_engine_count': 0,
                      'coverage': 'configured SearXNG instance and its enabled engines'}

    def search(self, query, *, limit=5):
        if not isinstance(query, str) or not query.strip() or len(query) > 600 or not 1 <= limit <= 20:
            raise SearchError('SEARCH_PROVIDER_ERROR')
        if self._last_call is not None:
            time.sleep(max(0, 1 - (time.monotonic() - self._last_call)))
        self._last_call = time.monotonic()
        url = self.instance_url + '/search?' + urlencode({'q': query, 'format': 'json',
                                                         'categories': 'general', 'pageno': 1})
        try:
            body, media = self.fetcher.fetch(url)
            if media != 'application/json':
                raise SearchError('SEARCH_PROVIDER_ERROR')
            payload = json.loads(body)
            if not isinstance(payload, dict) or not isinstance(payload.get('results'), list):
                raise SearchError('SEARCH_PROVIDER_ERROR')
            failed = payload.get('unresponsive_engines', [])
            if not isinstance(failed, list):
                raise SearchError('SEARCH_PROVIDER_ERROR')
            self.audit['unresponsive_engine_count'] += len(failed)
            # Even partial engine outages mean the configured search did not
            # fully succeed. Do not turn that into a factual insufficiency verdict.
            if failed:
                raise SearchError('SEARCH_PROVIDER_ERROR')
            results = []
            for rank, row in enumerate(payload['results'][:limit], 1):
                if not isinstance(row, dict):
                    raise SearchError('SEARCH_PROVIDER_ERROR')
                fields = [row.get('title', ''), row.get('url'), row.get('content', '')]
                if any(not isinstance(v, str) or len(v) > bound
                       for v, bound in zip(fields, (2000, 4096, 10000))):
                    raise SearchError('SEARCH_PROVIDER_ERROR')
                results.append(SearchResult(fields[0], fields[1], fields[2], self.name, rank, now()))
            return results
        except FetchError as exc:
            code = ('SEARCH_AUTH_FAILED' if exc.status in (401, 403) else
                    'SEARCH_RATE_LIMITED' if exc.status == 429 else 'SEARCH_PROVIDER_ERROR')
            raise SearchError(code) from None
        except SearchError:
            raise
        except Exception:
            raise SearchError('SEARCH_PROVIDER_ERROR') from None

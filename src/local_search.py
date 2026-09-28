"""Free, bounded authoritative-site crawl and private lexical discovery index."""
import contextlib
import io
import json
import os
import time
import uuid
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from research_search import external_directory, safe_file, tokens
from search_discovery import SearchResult, SearchError, normalize_url
from verification_models import digest, now
from web_sources import Fetcher, parse_document


class LocalSearchProvider:
    name = 'local'

    def __init__(self, base, policy, max_pages=12, refresh=False):
        self.base = external_directory(base)
        self.policy = policy
        if not 1 <= max_pages <= 30:
            raise ValueError('Invalid crawl bound')
        self.max_pages, self.refresh = max_pages, refresh
        self.entries = None
        self.audit = {'coverage': 'bounded approved-site index, not whole-web search',
                      'cache_used': False, 'events': [], 'max_pages': max_pages}
        self.policy_hash = digest(json.dumps(policy.rules, sort_keys=True))

    def _load(self):
        if self.refresh:
            return False
        for path in sorted(self.base.glob('local-index-*.json'), reverse=True)[:5]:
            try:
                path = safe_file(self.base, path.name)
                if path.stat().st_size > 2_000_000:
                    continue
                saved = json.loads(path.read_text(encoding='utf-8'))
                age = time.time() - saved['created_epoch']
                if (not 0 <= age < 86400 or saved['policy_hash'] != self.policy_hash
                        or saved['max_pages'] != self.max_pages):
                    continue
                entries = saved['entries']
                if not isinstance(entries, list) or not 0 < len(entries) <= self.max_pages:
                    continue
                if any(not isinstance(e, dict) or not isinstance(e.get('text'), str)
                       or len(e['text']) > 20000 or not isinstance(e.get('title'), str)
                       or len(e['title']) > 2000 or not isinstance(e.get('retrieved_at'), str)
                       or not self.policy.qualify(normalize_url(e['url']))['allowed'] for e in entries):
                    continue
                self.entries = entries
                self.audit.update(cache_used=True, indexed_at=saved['indexed_at'],
                                  indexed_pages=len(entries), events=saved['events'])
                return True
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return False

    def _crawl(self):
        self.entries = []
        queue = []
        for host, rule in self.policy.rules.items():
            if rule.get('allowed'):
                for seed in rule.get('crawl_seeds', ['https://' + host + '/']):
                    try:
                        url = normalize_url(seed)
                        if urlsplit(url).hostname == host and self.policy.qualify(url)['allowed']:
                            queue.append((url, 0))
                    except (ValueError, TypeError):
                        continue
        queue = queue[:100]
        robots, seen, attempts = {}, set(), 0
        fetcher = Fetcher(self.policy, timeout=10)
        while queue and attempts < self.max_pages:
            url, depth = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            host = urlsplit(url).hostname
            attempts += 1  # Includes blocked/failed pages: always bounded.
            if host not in robots:
                try:
                    body, _ = fetcher.fetch('https://' + host + '/robots.txt')
                    parser = RobotFileParser()
                    parser.parse(body.decode('utf-8', errors='strict').splitlines())
                    robots[host] = parser
                except Exception:
                    robots[host] = None  # Fail closed, including unavailable robots.
                time.sleep(1)
            parser = robots[host]
            if parser is None or not parser.can_fetch('TechnicalResearchEngine', url):
                self.audit['events'].append({'url': url, 'status': 'ROBOTS_BLOCKED_OR_UNAVAILABLE'})
                continue
            delay = max(1, parser.crawl_delay('TechnicalResearchEngine') or 1)
            rate = parser.request_rate('TechnicalResearchEngine')
            if rate and rate.requests:
                delay = max(delay, rate.seconds / rate.requests)
            if delay > 10:
                self.audit['events'].append({'url': url, 'status': 'CRAWL_DELAY_EXCEEDS_BUDGET'})
                continue
            try:
                body, media = fetcher.fetch(url)
                with contextlib.redirect_stderr(io.StringIO()):
                    doc = parse_document(url, body, media, self.policy)
                self.entries.append({'url': url, 'title': doc.source.title[:2000],
                                     'text': doc.text[:20000], 'retrieved_at': doc.source.retrieval_date})
                self.audit['events'].append({'url': url, 'status': 'INDEXED'})
                if depth == 0:
                    for link in doc.source.attributed_to:
                        try:
                            link = normalize_url(link)
                            if (urlsplit(link).hostname == host and not urlsplit(link).query
                                    and self.policy.qualify(link)['allowed'] and len(queue) < 100):
                                queue.append((link, 1))
                        except (ValueError, TypeError):
                            continue
            except Exception:
                self.audit['events'].append({'url': url, 'status': 'FETCH_OR_PARSE_FAILED'})
            finally:
                time.sleep(delay)
        self.audit.update(indexed_at=now(), indexed_pages=len(self.entries), page_attempts=attempts)
        if not self.entries:
            raise SearchError('SEARCH_PROVIDER_ERROR')
        saved = dict(entries=self.entries, created_epoch=time.time(), indexed_at=self.audit['indexed_at'],
                     policy_hash=self.policy_hash, max_pages=self.max_pages, events=self.audit['events'])
        # Immutable snapshots only, never follow/overwrite a user-supplied filename.
        name = 'local-index-' + str(time.time_ns()) + '-' + uuid.uuid4().hex + '.json'
        fd = os.open(self.base / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(saved, stream, ensure_ascii=False)

    def search(self, query, *, limit=5):
        if self.entries is None and not self._load():
            self._crawl()
        terms = set(tokens(query))
        ranked = sorted(((len(terms & set(tokens(e['title'] + ' ' + e['text']))), e)
                         for e in self.entries), key=lambda item: -item[0])
        return [SearchResult(e['title'], e['url'], '', self.name, i, e['retrieved_at'])
                for i, (score, e) in enumerate((item for item in ranked if item[0]), 1)
                if i <= limit]

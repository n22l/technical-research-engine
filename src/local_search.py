"""Bounded, incremental authoritative-site index. Discovery is never evidence."""
import contextlib
from collections import Counter, deque
import io
from html.parser import HTMLParser
import json
import os
import time
import uuid
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit, urljoin
from urllib.robotparser import RobotFileParser

from research_search import external_directory, safe_file, keyword_scores
from search_discovery import SearchResult, SearchError, normalize_url
from verification_models import digest, now
from web_sources import Fetcher, FetchError, parse_document




class IndexText(HTMLParser):
    """Drop obvious navigation and executable boilerplate from ranking only."""
    excluded = {'nav', 'header', 'footer', 'script', 'style', 'noscript'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocked = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.excluded:
            self.blocked += 1

    def handle_endtag(self, tag):
        if tag in self.excluded:
            self.blocked = max(0, self.blocked - 1)

    def handle_data(self, data):
        if not self.blocked:
            self.parts.append(data)


def discovery_links(body, base):
    """Bounded sitemap/RSS/Atom parser; no DTDs, entities or external resolution."""
    if len(body) > 2_000_000 or b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():
        raise ValueError('Unsafe discovery XML')
    root = ET.fromstring(body.decode('utf-8-sig'))
    kind = root.tag.rsplit('}', 1)[-1]
    if kind not in ('urlset', 'sitemapindex', 'rss', 'feed'):
        raise ValueError('Unknown discovery XML')
    links = []
    for node in root.iter():
        tag = node.tag.rsplit('}', 1)[-1]
        if tag == 'loc' or (tag == 'link' and node.get('rel', 'alternate') == 'alternate'):
            value = node.get('href') or node.text or ''
            if value.strip():
                links.append((urljoin(base, value.strip()), 'map' if kind == 'sitemapindex' else 'page'))
        if len(links) >= 1000:
            break
    return links


class LocalSearchProvider:
    name = 'local'

    def __init__(self, base, policy, max_pages=500, refresh=False, *, per_host=100, max_depth=2, max_seconds=120):
        self.base = external_directory(base)
        self.policy = policy
        if not 1 <= max_pages <= 500 or not 1 <= per_host <= 100 or not 0 <= max_depth <= 3 or not 1 <= max_seconds <= 600:
            raise ValueError('Invalid crawl bound')
        self.max_pages, self.refresh = max_pages, refresh
        self.per_host, self.max_depth, self.max_seconds = per_host, max_depth, max_seconds
        self.entries, self.frontier = None, []
        self.audit = {'coverage': 'bounded incremental approved-site index, not whole-web search',
                      'cache_used': False, 'events': [], 'max_pages': max_pages}
        self.policy_hash = digest(json.dumps(policy.rules, sort_keys=True))

    def _allowed(self, url):
        url = normalize_url(url)
        if not self.policy.qualify(url)['allowed']:
            raise ValueError('Unapproved URL')
        return url

    def _load(self):
        for path in sorted(self.base.glob('local-index-*.json'), reverse=True)[:5]:
            try:
                path = safe_file(self.base, path.name)
                if path.stat().st_size > 40_000_000:
                    continue
                saved = json.loads(path.read_text(encoding='utf-8'))
                if saved.get('schema') not in (2, 3) or saved['policy_hash'] != self.policy_hash or saved['max_pages'] != self.max_pages:
                    continue
                entries = saved['entries']
                if not isinstance(entries, list) or not 0 < len(entries) <= self.max_pages:
                    continue
                for e in entries:
                    if (not isinstance(e['text'], str) or len(e['text']) > 20000 or
                        not isinstance(e['title'], str) or len(e['title']) > 2000 or
                        not isinstance(e['retrieved_at'], str) or not isinstance(e['epoch'], (float, int))):
                        raise ValueError('Invalid cached entry')
                    self._allowed(e['url'])
                frontier = saved.get('frontier', [])
                if not isinstance(frontier, list) or len(frontier) > 3000:
                    continue
                for url, depth, kind in frontier:
                    self._allowed(url)
                    if type(depth) is not int or not 0 <= depth <= 3 or kind not in ('page', 'map'):
                        raise ValueError('Invalid frontier')
                self.entries, self.frontier = entries, frontier
                fresh = 0 <= time.time() - saved['created_epoch'] < 86400
                self.audit.update(cache_used=True, indexed_at=saved['indexed_at'], indexed_pages=len(entries),
                                  pending_urls=len(frontier), stale_pages=sum(time.time() - e['epoch'] >= 86400 for e in entries),
                                  hosts=sorted({urlsplit(e['url']).hostname for e in entries}))
                return fresh and not self.refresh and saved.get('schema') == 3
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return False

    def _crawl(self):
        retained = {e['url']: e for e in (self.entries or [])}
        queue, queued = deque(), set()
        def enqueue(url, depth=0, kind='page', front=False):
            try:
                url = self._allowed(url)
                if url not in queued and len(queued) < 3000 and depth <= self.max_depth:
                    queued.add(url)
                    item = (url, depth, kind)
                    queue.appendleft(item) if front else queue.append(item)
            except (ValueError, TypeError):
                pass
        # Reserve seed slots before a large saved frontier fills the queue.
        for host, rule in self.policy.rules.items():
            if not rule.get('allowed'):
                continue
            for seed in rule.get('crawl_seeds', ['https://' + host + '/']):
                enqueue(seed)
            for url in rule.get('sitemaps', []):
                enqueue(url, kind='map')
            for url in rule.get('feeds', []):
                enqueue(url, kind='map')
        for item in self.frontier:
            enqueue(*item)
        pending = {item[0] for item in self.frontier}
        queue = deque(sorted(queue, key=lambda item: item[0] not in pending))
        for e in retained.values():
            if time.time() - e['epoch'] >= 86400:
                enqueue(e['url'])
        robots, hosts, maps = {}, Counter(), Counter()
        indexed_hosts = Counter(urlsplit(url).hostname for url in retained)
        deferred, attempts = [], 0
        started = time.monotonic()
        fetcher = Fetcher(self.policy, max_bytes=2_000_000, timeout=10,
                          accept='text/html, application/pdf, application/xml, text/xml, application/rss+xml, application/atom+xml')
        while queue and attempts < self.max_pages and time.monotonic() - started < self.max_seconds:
            # Share the attempt budget across hosts; underrepresented hosts win ties.
            # A sitemap may add thousands of links without monopolizing the crawl.
            index = min(range(len(queue)), key=lambda i: (
                hosts[urlsplit(queue[i][0]).hostname],
                indexed_hosts[urlsplit(queue[i][0]).hostname]))
            queue.rotate(-index)
            url, depth, kind = queue.popleft()
            queue.rotate(index)
            host = urlsplit(url).hostname
            if hosts[host] >= self.per_host:
                deferred.append((url, depth, kind))
                continue
            if kind == 'page' and url in retained and not self.refresh and time.time() - retained[url]['epoch'] < 86400:
                continue
            if kind == 'map' and maps[host] >= 5:
                continue
            attempts += 1
            hosts[host] += 1
            if host not in robots:
                try:
                    body, media = fetcher.fetch('https://' + host + '/robots.txt')
                    if media != 'text/plain':
                        raise ValueError('Invalid robots')
                    parser = RobotFileParser()
                    parser.parse(body.decode('utf-8', errors='strict').splitlines())
                    robots[host] = parser
                    for sitemap in (parser.site_maps() or [])[:5]:
                        if urlsplit(sitemap).hostname == host:
                            enqueue(sitemap, kind='map', front=True)
                except FetchError as exc:
                    if exc.status in (404, 410):
                        parser = RobotFileParser()
                        parser.parse([])
                        robots[host] = parser
                        self.audit['events'].append({'url': 'https://' + host + '/robots.txt',
                                                     'status': 'ROBOTS_NOT_PRESENT'})
                    else:
                        robots[host] = None
                except Exception:
                    robots[host] = None
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
                if kind == 'map':
                    maps[host] += 1
                    for link, child_kind in discovery_links(body, url):
                        if urlsplit(link).hostname == host:
                            enqueue(link, depth, child_kind)
                    self.audit['events'].append({'url': url, 'status': 'DISCOVERY_FEED_READ'})
                    continue
                with contextlib.redirect_stderr(io.StringIO()):
                    doc = parse_document(url, body, media, self.policy)
                index_text = doc.text
                if media == 'text/html':
                    cleaner = IndexText()
                    cleaner.feed(body.decode('utf-8', errors='replace'))
                    index_text = ' '.join(cleaner.parts)
                if url in retained or len(retained) < self.max_pages:
                    retained[url] = {'url': url, 'title': doc.source.title[:2000],
                                     'text': index_text[:20000], 'retrieved_at': doc.source.retrieval_date,
                                     'epoch': time.time()}
                self.audit['events'].append({'url': url, 'status': 'INDEXED'})
                if depth < self.max_depth:
                    for link in doc.source.attributed_to:
                        if urlsplit(link).hostname == host and not urlsplit(link).query:
                            enqueue(link, depth + 1)
            except Exception:
                self.audit['events'].append({'url': url, 'status': 'FETCH_OR_PARSE_FAILED'})
            finally:
                time.sleep(delay)
        self.entries = list(retained.values())
        self.frontier = (list(queue) + deferred)[:3000]
        self.audit.update(indexed_at=now(), indexed_pages=len(self.entries), page_attempts=attempts,
                          pending_urls=len(self.frontier), cache_used=bool(retained) and self.audit['cache_used'],
                          stale_pages=sum(time.time() - e['epoch'] >= 86400 for e in self.entries),
                          budget_exhausted=bool(queue), hosts=sorted({urlsplit(e['url']).hostname for e in self.entries}))
        if not self.entries:
            raise SearchError('SEARCH_PROVIDER_ERROR')
        saved = dict(schema=3, entries=self.entries, frontier=self.frontier, created_epoch=time.time(),
                     indexed_at=self.audit['indexed_at'], policy_hash=self.policy_hash, max_pages=self.max_pages)
        name = 'local-index-' + str(time.time_ns()) + '-' + uuid.uuid4().hex + '.json'
        fd = os.open(self.base / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(saved, stream, ensure_ascii=False)

    def search(self, query, *, limit=5):
        if self.entries is None and not self._load():
            self._crawl()
        scores = keyword_scores([e['text'] for e in self.entries], query,
                                [e['title'] for e in self.entries])
        ranked = [(score, e) for score, e in zip(scores, self.entries) if score > 0]
        ranked.sort(key=lambda item: (-item[0], item[1]['url']))
        return [SearchResult(e['title'], e['url'], '', self.name, i, e['retrieved_at'])
                for i, (_, e) in enumerate(ranked[:limit], 1)]

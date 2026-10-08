"""Bounded, incremental authoritative-site index. Discovery is never evidence."""
import contextlib
from collections import Counter, deque
import io
import gzip
from html.parser import HTMLParser
import json
import os
import time
import uuid
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit, urljoin
from urllib.parse import parse_qsl
from dataclasses import asdict
import re
from urllib.robotparser import RobotFileParser

from research_search import external_directory, safe_file, keyword_scores
from search_discovery import SearchResult, SearchError, normalize_url
from verification_models import digest, now
from web_sources import Fetcher, FetchError, parse_document
from retrieval_constraints import coverage, page_weight




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


def discovery_links(body, base, max_urls=50000):
    """Bounded sitemap/RSS/Atom parser; no DTDs, entities or external resolution."""
    if len(body) > 2_000_000:
        raise ValueError('Oversized discovery file')
    if body.startswith(b'\x1f\x8b'):
        with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:
            body = stream.read(2_000_001)
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
        if len(links) >= max_urls:
            break
    return links


class LocalSearchProvider:
    name = 'local'

    def __init__(self, base, policy, max_pages=500, refresh=False, *, per_host=100, max_depth=2, max_seconds=120,
                 max_sitemap_depth=8, max_sitemap_files=100, max_urls_discovered=20000, publisher_filter=None):
        self.base = external_directory(base)
        self.policy = policy
        if not 1 <= max_pages <= 500 or not 1 <= per_host <= 100 or not 0 <= max_depth <= 3 or not 1 <= max_seconds <= 600:
            raise ValueError('Invalid crawl bound')
        self.max_pages, self.refresh = max_pages, refresh
        self.per_host, self.max_depth, self.max_seconds = per_host, max_depth, max_seconds
        if not 1 <= max_sitemap_depth <= 20 or not 1 <= max_sitemap_files <= 1000 or not 100 <= max_urls_discovered <= 100000:
            raise ValueError('Invalid discovery bound')
        self.max_sitemap_depth, self.max_sitemap_files = max_sitemap_depth, max_sitemap_files
        self.max_urls_discovered, self.publisher_filter = max_urls_discovered, publisher_filter
        if publisher_filter:
            if publisher_filter in policy.rules:
                self.publisher_filter = policy.rules[publisher_filter]['publisher']
            if self.publisher_filter not in {r['publisher'] for r in policy.rules.values() if r.get('allowed')}:
                raise ValueError('Unknown publisher')
        self.inventory, self.maps_read = {}, set()
        self.entries, self.frontier = None, []
        self.audit = {'coverage': 'bounded incremental approved-site index, not whole-web search',
                      'cache_used': False, 'events': [], 'max_pages': max_pages}
        self.policy_hash = digest(json.dumps(policy.rules, sort_keys=True))

    def _allowed(self, url):
        url = normalize_url(url)
        if not self.policy.qualify(url)['allowed']:
            raise ValueError('Unapproved URL')
        p = urlsplit(url)
        if re.search(r'/(?:login|logout|account|calendar|search)(?:/|$)', p.path, re.I):
            raise ValueError('Crawl trap')
        if any(k.lower() in {'sort', 'filter', 'session', 'sid', 'page', 'offset', 'search', 'q'} for k, v in parse_qsl(p.query)):
            raise ValueError('Crawl trap')
        return url

    def _load(self):
        for path in sorted(self.base.glob('local-index-*.json'), reverse=True)[:5]:
            try:
                path = safe_file(self.base, path.name)
                if path.stat().st_size > 200_000_000:
                    continue
                saved = json.loads(path.read_text(encoding='utf-8'))
                if saved.get('schema') not in (2, 3, 4) or saved['max_pages'] != self.max_pages:
                    continue
                policy_changed = saved['policy_hash'] != self.policy_hash
                def still_allowed(url):
                    try: self._allowed(url); return True
                    except ValueError: return False
                entries = saved['entries']
                if not isinstance(entries, list) or not 0 <= len(entries) <= self.max_pages:
                    continue
                entries = [e for e in entries if still_allowed(e['url'])]
                for e in entries:
                    if (not isinstance(e['text'], str) or len(e['text']) > 20000 or
                        not isinstance(e['title'], str) or len(e['title']) > 2000 or
                        not isinstance(e['retrieved_at'], str) or not isinstance(e['epoch'], (float, int))):
                        raise ValueError('Invalid cached entry')
                    self._allowed(e['url'])
                    if 'passages' not in e: e['epoch'] = 0
                frontier = saved.get('frontier', [])
                if not isinstance(frontier, list) or len(frontier) > 100000:
                    continue
                frontier = [item for item in frontier if still_allowed(item[0])]
                for url, depth, kind in frontier:
                    self._allowed(url)
                    if type(depth) is not int or not 0 <= depth <= 20 or kind not in ('page', 'map'):
                        raise ValueError('Invalid frontier')
                self.entries, self.frontier = entries, frontier
                self.inventory = {u:v for u,v in saved.get('inventory', {}).items() if still_allowed(u)}
                self.maps_read = set(saved.get('maps_read', [])) if frontier and not policy_changed else set()
                self.audit['site_coverage'] = saved.get('site_coverage', [])
                fresh = 0 <= time.time() - saved['created_epoch'] < 86400
                self.audit.update(cache_used=True, indexed_at=saved['indexed_at'], indexed_pages=len(entries),
                                  pending_urls=len(frontier), stale_pages=sum(time.time() - e['epoch'] >= 86400 for e in entries),
                                  hosts=sorted({urlsplit(e['url']).hostname for e in entries}))
                return fresh and not self.refresh and not policy_changed and saved.get('schema') == 4
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return False

    def _crawl(self):
        retained = {e['url']: e for e in (self.entries or [])}
        other_frontier = [item for item in self.frontier if self.publisher_filter and
                          self.policy.qualify(item[0])['publisher'] != self.publisher_filter]
        queue, queued = deque(), set()
        truncated = False
        def same_publisher(a, b):
            try:
                rule = self.policy.qualify(a)
                return rule['allowed'] and rule['publisher'] == self.policy.qualify(b)['publisher']
            except ValueError:
                return False
        def enqueue(url, depth=0, kind='page', front=False):
            nonlocal truncated
            try:
                url = self._allowed(url)
                rule = self.policy.qualify(url)
                if self.publisher_filter and self.publisher_filter not in (rule['publisher'], urlsplit(url).hostname):
                    return
                if url not in self.inventory and len(self.inventory) >= self.max_urls_discovered:
                    truncated = True
                    return
                self.inventory.setdefault(url, {'kind': kind, 'status': 'PENDING'})
                depth_limit = self.max_sitemap_depth if kind == 'map' else self.max_depth
                if depth > depth_limit or len(queued) >= self.max_urls_discovered:
                    truncated = True
                    self.inventory[url]['status'] = 'DISCOVERY_LIMITED'
                    return
                if kind == 'map' and url in self.maps_read:
                    return
                if url not in queued:
                    queued.add(url)
                    item = (url, depth, kind)
                    queue.appendleft(item) if front else queue.append(item)
            except (ValueError, TypeError):
                pass
        # Reserve seed slots before a large saved frontier fills the queue.
        for host, rule in self.policy.rules.items():
            if not rule.get('allowed'):
                continue
            for url in rule.get('sitemaps', []):
                enqueue(url, kind='map')
            for url in rule.get('feeds', []):
                enqueue(url, kind='map')
            for seed in rule.get('crawl_seeds', ['https://' + host + '/']):
                enqueue(seed)
        for item in self.frontier:
            enqueue(*item)
        for url, state in list(self.inventory.items()):
            if state['status'] == 'FETCH_FAILED':
                enqueue(url, state.get('depth', 0), state['kind'])
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
            prefer_pages = sum(maps.values()) >= 2 * (attempts + 1)
            index = min(range(len(queue)), key=lambda i: (
                (queue[i][2] != 'page') if prefer_pages else (queue[i][2] != 'map'),
                hosts[urlsplit(queue[i][0]).hostname] + maps[urlsplit(queue[i][0]).hostname],
                indexed_hosts[urlsplit(queue[i][0]).hostname]))
            queue.rotate(-index)
            url, depth, kind = queue.popleft()
            queue.rotate(index)
            host = urlsplit(url).hostname
            if self.inventory[url].get('retry_after', 0) > time.time():
                deferred.append((url, depth, kind))
                continue
            if hosts[host] >= self.per_host:
                deferred.append((url, depth, kind))
                continue
            if kind == 'page' and url in retained and not self.refresh and time.time() - retained[url]['epoch'] < 86400:
                continue
            if kind == 'map' and maps[host] >= self.max_sitemap_files:
                deferred.append((url, depth, kind))
                continue
            if kind == 'page':
                attempts += 1
                hosts[host] += 1
            else:
                maps[host] += 1  # Failed/blocked maps consume the discovery budget too.
            if host not in robots:
                try:
                    fetcher.validators = {}
                    body, media = fetcher.fetch('https://' + host + '/robots.txt')
                    if media != 'text/plain':
                        raise ValueError('Invalid robots')
                    parser = RobotFileParser()
                    parser.parse(body.decode('utf-8', errors='strict').splitlines())
                    robots[host] = parser
                    for sitemap in (parser.site_maps() or []):
                        if same_publisher(sitemap, url):
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
                if kind == 'page' and any(item[2] == 'map' for item in queue):
                    queue.append((url, depth, kind))
                    attempts -= 1
                    hosts[host] -= 1
                    continue
            parser = robots[host]
            if parser is None or not parser.can_fetch('TechnicalResearchEngine', url):
                self.inventory[url]['status'] = 'ROBOTS_BLOCKED'
                self.audit['events'].append({'url': url, 'status': 'ROBOTS_BLOCKED_OR_UNAVAILABLE'})
                continue
            delay = max(1, parser.crawl_delay('TechnicalResearchEngine') or 1)
            rate = parser.request_rate('TechnicalResearchEngine')
            if rate and rate.requests:
                delay = max(delay, rate.seconds / rate.requests)
            if delay > 10:
                self.inventory[url]['status'] = 'ROBOTS_BLOCKED'
                self.audit['events'].append({'url': url, 'status': 'CRAWL_DELAY_EXCEEDS_BUDGET'})
                continue
            try:
                self.inventory[url]['attempts'] = self.inventory[url].get('attempts', 0) + 1
                self.inventory[url]['depth'] = depth
                old = retained.get(url, {}) if kind == 'page' else {}
                fetcher.validators = {k: old.get(v) for k, v in [('If-None-Match', 'etag'), ('If-Modified-Since', 'last_modified')]}
                body, media = fetcher.fetch(url)
                self.inventory[url].pop('retry_after', None)
                if body is None:
                    if not old: raise ValueError('Unexpected not-modified response')
                    old['epoch'], old['retrieved_at'] = time.time(), now()
                    self.inventory[url]['status'] = 'INDEXED'
                    continue
                if kind == 'map':
                    links = discovery_links(body, url, self.max_urls_discovered + 1)
                    if len(links) >= self.max_urls_discovered + 1: truncated = True
                    for link, child_kind in links:
                        if same_publisher(link, url):
                            enqueue(link, depth+1 if child_kind == 'map' else 0, child_kind)
                    if not truncated: self.maps_read.add(url)
                    self.inventory[url]['status'] = 'DISCOVERY_LIMITED' if truncated else 'READ'
                    self.audit['events'].append({'url': url, 'status': 'DISCOVERY_FEED_READ'})
                    continue
                with contextlib.redirect_stderr(io.StringIO()):
                    doc = parse_document(url, body, media, self.policy)
                if len(doc.text) > 200000 or len(doc.passages) > 2000:
                    raise ValueError('Parsed document exceeds index bound')
                index_text = doc.text
                if media == 'text/html':
                    cleaner = IndexText()
                    cleaner.feed(body.decode('utf-8', errors='replace'))
                    index_text = ' '.join(cleaner.parts)
                if url in retained or len(retained) < self.max_pages:
                    capture = 'crawl-capture-' + doc.source.content_hash + '.bin'
                    try:
                        fd = os.open(self.base / capture, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                        with os.fdopen(fd, 'wb') as stream: stream.write(body)
                    except FileExistsError:
                        if digest(safe_file(self.base, capture).read_bytes()) != doc.source.content_hash:
                            raise ValueError('Capture hash mismatch')
                    retained[url] = {'url': url, 'title': doc.source.title[:2000],
                                     'text': index_text[:20000], 'retrieved_at': doc.source.retrieval_date,
                                     'source': asdict(doc.source), 'capture': capture, 'media_type': media,
                                     **fetcher.response_metadata,
                                     'passages': [dict(p, location=asdict(p['location'])) for p in doc.passages],
                                     'epoch': time.time()}
                    self.inventory[url]['status'] = 'INDEXED'
                else:
                    deferred.append((url, depth, kind))
                    truncated = True
                self.audit['events'].append({'url': url, 'status': 'INDEXED'})
                if depth < self.max_depth:
                    for link in doc.source.attributed_to:
                        if same_publisher(link, url):
                            enqueue(link, depth + 1)
                elif doc.source.attributed_to:
                    for link in doc.source.attributed_to:
                        try:
                            target = self._allowed(link)
                            if target not in self.inventory and self.policy.qualify(target)['publisher'] == self.policy.qualify(url)['publisher']:
                                enqueue(target, depth + 1)
                        except ValueError:
                            pass
            except Exception:
                self.inventory[url]['status'] = 'FETCH_FAILED'
                self.inventory[url]['retry_after'] = time.time() + min(86400, 300 * 2 ** min(self.inventory[url].get('attempts', 1)-1, 8))
                deferred.append((url, depth, kind))
                self.audit['events'].append({'url': url, 'status': 'FETCH_OR_PARSE_FAILED'})
            finally:
                time.sleep(delay)
        self.entries = list(retained.values())
        self.frontier = (other_frontier + list(queue) + deferred)[:self.max_urls_discovered]
        self.audit.update(indexed_at=now(), indexed_pages=len(self.entries), page_attempts=attempts,
                          sitemap_attempts=sum(maps.values()),
                          pending_urls=len(self.frontier), cache_used=bool(retained) and self.audit['cache_used'],
                          stale_pages=sum(time.time() - e['epoch'] >= 86400 for e in self.entries),
                          budget_exhausted=bool(queue or deferred or truncated), hosts=sorted({urlsplit(e['url']).hostname for e in self.entries}))
        self._coverage(truncated)
        self._save()
        if not self.entries: raise SearchError('SEARCH_PROVIDER_ERROR')

    def _coverage(self, truncated=False):
        rows = []
        for publisher in sorted({r['publisher'] for r in self.policy.rules.values() if r.get('allowed')}):
            hosts = [h for h, r in self.policy.rules.items() if r.get('allowed') and r['publisher'] == publisher]
            items = [v for u, v in self.inventory.items() if urlsplit(u).hostname in hosts]
            counts = Counter(v['status'] for v in items)
            pending = sum(urlsplit(u).hostname in hosts for u, _, _ in self.frontier)
            limited = counts['DISCOVERY_LIMITED'] or counts['PENDING'] or pending or truncated
            status = ('BUDGET_LIMITED' if limited else 'ROBOTS_LIMITED' if counts['ROBOTS_BLOCKED'] else
                      'FETCH_LIMITED' if counts['FETCH_FAILED'] else 'UNKNOWN' if not items else 'COMPLETE_WITHIN_DISCOVERED_SCOPE')
            rows.append(dict(publisher=publisher, approved_hosts=hosts, discovered_urls=len(items),
                configured_seeds=[u for h in hosts for u in self.policy.rules[h].get('crawl_seeds', ['https://'+h+'/'])],
                pages_attempted=sum(v.get('attempts',0) for v in items if v['kind']=='page'),
                indexed_urls=counts['INDEXED'], pending_urls=pending, blocked_urls=counts['ROBOTS_BLOCKED'],
                failed_urls=counts['FETCH_FAILED'], sitemap_urls=sum(v['kind']=='map' for v in items),
                status=status, updated_at=now()))
        self.audit['site_coverage'] = rows

    def _save(self):
        saved = dict(schema=4, entries=self.entries, frontier=self.frontier, created_epoch=time.time(),
                     inventory=self.inventory, maps_read=sorted(self.maps_read), site_coverage=self.audit.get('site_coverage', []),
                     indexed_at=self.audit['indexed_at'], policy_hash=self.policy_hash, max_pages=self.max_pages)
        name = 'local-index-' + str(time.time_ns()) + '-' + uuid.uuid4().hex + '.json'
        fd = os.open(self.base / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(saved, stream, ensure_ascii=False)

    def search(self, query, *, limit=5):
        if self.entries is None and not self._load():
            self._crawl()
        from passage_ranking import rank_passages
        entries = [e for e in self.entries if not self.publisher_filter or self.publisher_filter in
                   (self.policy.qualify(e['url'])['publisher'], urlsplit(e['url']).hostname)]
        passages = [dict(p, source=dict(p['source'], title=e['title'])) for e in entries for p in e.get('passages', [])]
        hits = rank_passages(passages, query, limit=max(1, len(passages)), per_document=1)
        by_source = {h['source']['id']: h for h in hits}
        legacy = keyword_scores([e['text'] for e in entries], query, [e['title'] for e in entries])
        ranked = []
        for e, oldscore in zip(entries, legacy):
            hit = by_source.get(e.get('source', {}).get('source_id'))
            score = hit['score'] if hit else oldscore if 'passages' not in e else 0
            if score > 0: ranked.append((score * page_weight(e['url']), e, hit))
        diagnostic = coverage(query, [e['title'] + ' ' + e['text'] for e in self.entries])
        if ranked:
            diagnostic['status'] = 'MATCHES_FOUND'
        diagnostic['matching_pages'] = len(ranked)
        diagnostic.update(query=query, indexed_documents=len(entries), number_of_passages=len(passages),
                          matching_passages=len(hits), category='MATCH_FOUND' if ranked else
                          'CRAWL_BLOCKED' if any(c['blocked_urls'] for c in self.audit.get('site_coverage', [])) else
                          'INDEX_COVERAGE_INCOMPLETE' if self.frontier else 'NO_MATCH')
        from research_search import keyword_tokens
        diagnostic.update(tokens=list(keyword_tokens(query)), legacy_pages=sum('passages' not in e for e in entries),
                          top_match=hits[0]['retrieval_match'] if hits else None)
        self.audit.setdefault('query_diagnostics', []).append(diagnostic)
        ranked.sort(key=lambda item: (-item[0], item[1]['url']))
        return [SearchResult(e['title'], e['url'], '', self.name, i, e['retrieved_at'],
                            dict(hit['retrieval_match'], paragraph=hit['passage']) if hit else {})
                for i, (_, e, hit) in enumerate(ranked[:limit], 1)]

    def reindex(self):
        self._load()
        missing = 0
        for e in self.entries or []:
            if not e.get('capture'):
                missing += 1; continue
            body = safe_file(self.base, e['capture']).read_bytes()
            if digest(body) != e['source']['content_hash']: raise ValueError('Capture hash mismatch')
            doc = parse_document(e['url'], body, e['media_type'], self.policy)
            e['passages'] = [dict(p, location=asdict(p['location'])) for p in doc.passages]
        if self.entries is None: raise SearchError('SEARCH_UNAVAILABLE')
        self.audit.setdefault('indexed_at', now())
        self._save()
        return {'reindexed': len(self.entries)-missing, 'legacy_entries_require_refetch': missing}

"""Policy, inert parsing, and bounded public HTTPS fetching. No browser execution."""
import http.client
import io
import ipaddress
import json
import re
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import urlsplit, urljoin
from datetime import date
from pathlib import Path
import posixpath
from urllib.parse import unquote
from verification_models import SourceRecord, Document, EvidenceLocation, digest, now


def public_url(url):
    p = urlsplit(url)
    if (p.scheme != 'https' or not p.hostname or p.username or p.password
            or p.port not in (None, 443) or any(ord(c) < 33 for c in url)):
        raise ValueError('Only public HTTPS URLs without credentials are accepted')
    if p.hostname.lower() == 'localhost':
        raise ValueError('Nonpublic destination')
    return p


class SourcePolicy:
    def __init__(self, rules):
        self.rules = {host: dict(rule) for host, rule in rules.items()}
        for host, rule in list(self.rules.items()):
            for child in rule.get('crawl_hosts', []):
                if not isinstance(child, str) or child != child.lower() or public_url('https://' + child).hostname != child:
                    raise ValueError('Invalid explicit crawl host')
                if child not in self.rules:
                    self.rules[child] = dict(rule, crawl_hosts=[], crawl_seeds=['https://' + child + '/'], sitemaps=[], feeds=[])

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text(encoding='utf-8'))['sources'])

    def qualify(self, url):
        host = public_url(url).hostname.lower()
        # Exact host rules win; subdomains require explicit opt-in.
        for domain, rule in sorted(self.rules.items(), key=lambda x: -len(x[0])):
            if host == domain or (rule.get('include_subdomains', False) and host.endswith('.' + domain)):
                path = posixpath.normpath(unquote(urlsplit(url).path or '/'))
                if '%' in path or '\\' in path:
                    return dict(rule, allowed=False, registered=True)
                if urlsplit(url).path.endswith('/') and not path.endswith('/'): path += '/'
                prefixes = rule.get('allowed_path_prefixes', ['/'])
                excluded = rule.get('excluded_path_prefixes', [])
                permitted = path == '/robots.txt' or (any(path.startswith(p) for p in prefixes)
                             and not any(path.startswith(p) for p in excluded))
                return dict(rule, allowed=bool(rule.get('allowed') and permitted), registered=True)
        return {'allowed': False, 'tier': None, 'type': 'discovery_only', 'publisher': host, 'registered': False}


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.active = None
        self.parts = []
        self.blocks = []
        self.heading = None
        self.title = ''
        self.meta = {}
        self.links = []
        self.language = 'unknown'
        self.canonical = None
        self.in_main = 0
        self.main_blocks = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in {'main', 'article'}:
            self.flush()
            self.in_main += 1
        if tag in {'script', 'style', 'noscript', 'template', 'nav', 'header', 'footer', 'aside'}:
            self.hidden += 1
        if self.hidden:
            return
        if tag == 'html':
            self.language = a.get('lang', 'unknown')
        if tag == 'meta':
            self.meta[a.get('property', a.get('name', ''))] = a.get('content', '')
        if tag == 'link' and a.get('rel') == 'canonical':
            self.canonical = a.get('href')
        if tag == 'a' and a.get('href'):
            self.links.append(a['href'])
        if tag in {'p', 'li', 'h1', 'h2', 'h3', 'h4', 'title'}:
            self.flush()
            self.active = tag
        if tag == 'br' and self.active:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in {'main', 'article'}:
            self.flush()
            self.in_main = max(0, self.in_main - 1)
        if tag in {'script', 'style', 'noscript', 'template', 'nav', 'header', 'footer', 'aside'}:
            self.hidden = max(0, self.hidden - 1)
        elif not self.hidden and tag == self.active:
            self.flush()

    def handle_data(self, data):
        if self.active and not self.hidden:
            self.parts.append(data)

    def flush(self):
        text = ''.join(self.parts).strip()
        if text:
            if self.active == 'title':
                self.title = text
            elif self.active and self.active.startswith('h'):
                self.heading = text
            else:
                self.blocks.append((text, None, self.heading))
                if self.in_main:
                    self.main_blocks.append((text, None, self.heading))
        self.active, self.parts = None, []


def iso_date(value):
    try:
        return date.fromisoformat(value[:10]).isoformat() if value else None
    except ValueError:
        return None


def parse_document(url, body, media_type, policy):
    rule = policy.qualify(url)
    if not rule['allowed']:
        raise ValueError('SOURCE_NOT_ALLOWED')
    title, language, published, author, canonical, links = '', 'unknown', None, None, None, []
    if media_type == 'application/pdf':
        # Optional dependency; no OCR or invented printed page numbers.
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(body))
        if reader.is_encrypted or len(reader.pages) > 500:
            raise ValueError('Unsupported PDF')
        blocks = []
        for number, page in enumerate(reader.pages, 1):
            for paragraph in re.split(r'\n\s*\n', page.extract_text() or ''):
                if paragraph.strip():
                    blocks.append((paragraph.strip(), number, None))
        title = str((reader.metadata or {}).get('/Title', ''))
    elif media_type in {'text/html', 'application/xhtml+xml'}:
        parser = PageParser()
        parser.feed(body.decode('utf-8', errors='strict'))
        parser.flush()
        blocks, title, language = parser.main_blocks or parser.blocks, parser.title, parser.language
        published = iso_date(parser.meta.get('article:published_time') or parser.meta.get('date'))
        author = parser.meta.get('author')
        if parser.canonical:
            candidate = urljoin(url, parser.canonical)
            # A page cannot redirect authority or identity to another publisher.
            if urlsplit(candidate).hostname == urlsplit(url).hostname:
                canonical = candidate
        links = [urljoin(url, u) for u in parser.links]
    else:
        raise ValueError('Unsupported media type')
    if not blocks:
        raise ValueError('No extractable paragraphs')
    sid = digest(url + '\n' + digest(body))[:24]
    source = SourceRecord(sid, url, canonical, title, rule['publisher'], published, now(),
                          rule.get('tier'), rule['type'], language, urlsplit(url).hostname,
                          True, digest(body), author=author, jurisdiction=rule.get('jurisdiction'),
                          official=rule.get('official', False), primary_source=rule.get('primary', False))
    text, passages = '', []
    for i, (paragraph, page, heading) in enumerate(blocks, 1):
        start = len(text)
        text += paragraph + '\n\n'
        location = EvidenceLocation(sid, i, paragraph[:100], start, start + len(paragraph), page, heading)
        passages.append({'passage_id': f'{sid}:p{i}', 'passage': paragraph, 'location': location,
                         'source': {'id': sid, 'source_url': url}})
    doc = Document(source, text, passages)
    # Links are dependency hints, not evidence of independent confirmation.
    source.attributed_to = sorted(set(links))
    return doc


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        sock = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


class FetchError(ValueError):
    """HTTP status only; never response bodies or credentials."""
    def __init__(self, status):
        super().__init__('FETCH_FAILED')
        self.status = status


class Fetcher:
    def __init__(self, policy, max_bytes=4_000_000, timeout=15, accept='text/html, application/pdf'):
        self.policy, self.max_bytes, self.timeout = policy, max_bytes, timeout
        self.accept = accept
        self.validators = {}
        self.response_metadata = {}

    def fetch(self, url):
        # No redirects, proxies, cookies, authentication, or automatic retries.
        p = public_url(url)
        if not self.policy.qualify(url)['allowed']:
            raise ValueError('SOURCE_NOT_ALLOWED')
        addresses = {x[4][0] for x in socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)}
        if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
            raise ValueError('Nonpublic address')
        conn = PinnedHTTPS(p.hostname, sorted(addresses)[0], self.timeout)
        try:
            headers = {'User-Agent': 'TechnicalResearchEngine/0.2 (manual public-source research)',
                       'Accept': self.accept, 'Accept-Encoding': 'identity'}
            for name in ('If-None-Match', 'If-Modified-Since'):
                value = self.validators.get(name)
                if isinstance(value, str) and len(value) <= 1024 and not any(ord(c) < 32 for c in value):
                    headers[name] = value
            conn.request('GET', (p.path or '/') + ('?' + p.query if p.query else ''),
                         headers=headers)
            response = conn.getresponse()
            self.response_metadata = {'etag': response.getheader('ETag'), 'last_modified': response.getheader('Last-Modified')}
            if response.status == 304 and any(k in headers for k in ('If-None-Match', 'If-Modified-Since')):
                return None, None
            if response.status != 200:
                raise FetchError(response.status)
            if response.getheader('Content-Encoding', 'identity') != 'identity':
                raise ValueError('FETCH_FAILED')
            if int(response.getheader('Content-Length', '0')) > self.max_bytes:
                raise ValueError('Oversized response')
            body = response.read(self.max_bytes + 1)
            if len(body) > self.max_bytes:
                raise ValueError('Oversized response')
            return body, response.getheader('Content-Type', '').split(';')[0].strip().lower()
        finally:
            conn.close()

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
        self.rules = rules

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text(encoding='utf-8'))['sources'])

    def qualify(self, url):
        host = public_url(url).hostname.lower()
        # Exact host rules win; subdomains require explicit opt-in.
        for domain, rule in sorted(self.rules.items(), key=lambda x: -len(x[0])):
            if host == domain or (rule.get('include_subdomains', False) and host.endswith('.' + domain)):
                return dict(rule, registered=True)
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

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in {'script', 'style', 'noscript', 'template'}:
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
        if tag in {'script', 'style', 'noscript', 'template'}:
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
        blocks, title, language = parser.blocks, parser.title, parser.language
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


class Fetcher:
    def __init__(self, policy, max_bytes=4_000_000, timeout=15):
        self.policy, self.max_bytes, self.timeout = policy, max_bytes, timeout

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
            conn.request('GET', (p.path or '/') + ('?' + p.query if p.query else ''),
                         headers={'User-Agent': 'TechnicalResearchEngine/0.2 (manual public-source research)',
                                  'Accept': 'text/html, application/pdf', 'Accept-Encoding': 'identity'})
            response = conn.getresponse()
            if response.status != 200 or response.getheader('Content-Encoding', 'identity') != 'identity':
                raise ValueError('FETCH_FAILED')
            if int(response.getheader('Content-Length', '0')) > self.max_bytes:
                raise ValueError('Oversized response')
            body = response.read(self.max_bytes + 1)
            if len(body) > self.max_bytes:
                raise ValueError('Oversized response')
            return body, response.getheader('Content-Type', '').split(';')[0].strip().lower()
        finally:
            conn.close()

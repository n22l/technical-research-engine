"""Explicit lexical subject constraints; never an entailment or identity verdict."""
import re
import unicodedata
from urllib.parse import urlsplit

# Small, inspectable vocabulary. Unknown subjects retain normal lexical ranking.
GROUPS = {
    'china': ('china', 'chinese', '中国'),
    'india': ('india', 'indian', '印度'),
    'usa': ('united states', 'american', 'usa', '美国'),
    'japan': ('japan', 'japanese', '日本'),
    'russia': ('russia', 'russian', '俄罗斯'),
    'europe': ('europe', 'european', '欧洲'),
    'france': ('france', 'french', '法国'),
    'germany': ('germany', 'german', '德国'),
    'uk': ('united kingdom', 'british', '英国'),
    'webb': ('webb', 'jwst', '韦布', '韦伯'),
    'rocket': ('rocket', 'rockets', '火箭'),
    'reuse': ('reuse', 'reusable', 'reused', '重复使用', '复用'),
    'reflight': ('reflight', 're-flight', 'reflown', 'refly', '复飞'),
    'recovery': ('recovery', 'recovered', 'landing', 'landed', '回收', '着陆'),
    'l2': ('l2', 'second lagrange', '第二拉格朗日'),
}


def concepts(text):
    text = unicodedata.normalize('NFKC', text).lower()
    return {key for key, aliases in GROUPS.items() if any(
        (re.search(r'\b' + re.escape(alias) + r'\b', text) if alias.isascii() else alias in text)
        for alias in aliases)}


def subject_matches(query, text):
    return concepts(query) <= concepts(text)


def coverage(query, texts):
    required = concepts(query)
    seen = set().union(*(concepts(t) for t in texts)) if texts else set()
    missing = sorted(required - seen)
    return {'required_subjects': sorted(required), 'missing_subjects': missing,
            'status': 'MISSING_COVERAGE' if not texts or missing else 'WEAK_RELEVANCE'}


def page_weight(url):
    """Downweight recognizable home/list pages; not proof a URL is an article."""
    path = urlsplit(url).path.lower().strip('/')
    if path in ('', 'en', 'cn', 'zh', 'index.html', 'en/index.html'):
        return .2
    if path.endswith(('index.html', 'news', 'news.html', 'about-us')) or '/list/' in '/' + path:
        return .5
    return 1.0

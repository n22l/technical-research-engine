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
    'spacex': ('spacex', 'space x', '太空探索技术公司'),
    'stoke': ('stoke space', 'stokespace'),
    'blue_origin': ('blue origin', '蓝色起源'),
    'landspace': ('landspace', '蓝箭航天'),
    'falcon9': ('falcon 9', 'falcon-9', '猎鹰9', '猎鹰九号'),
    'falcon_heavy': ('falcon heavy', '重型猎鹰'),
    'starship': ('starship', '星舰'),
    'zhuque3': ('zhuque-3', 'zhuque 3', 'zq-3', '朱雀三号'),
}

COUNTRIES = {'china', 'india', 'usa', 'japan', 'russia', 'europe', 'france', 'germany', 'uk'}
COMPANIES = {'spacex', 'stoke', 'blue_origin', 'landspace'}
VEHICLES = {'falcon9', 'falcon_heavy', 'starship', 'zhuque3'}
IDENTITIES = COUNTRIES | COMPANIES | VEHICLES | {'webb'}


def mission_ids(text):
    """Preserve explicit numbered mission identity; Crew-13 is not Crew-12."""
    text = unicodedata.normalize('NFKC', text).lower()
    return {prefix + '-' + number for prefix, number in
            re.findall(r'(?<![a-z0-9])(crew|crs|artemis)[\s-]*(\d+)(?![a-z0-9])', text)}


def concepts(text):
    text = unicodedata.normalize('NFKC', text).lower()
    return {key for key, aliases in GROUPS.items() if any(
        (re.search(r'(?<![a-z0-9])' + re.escape(alias) + r'(?![a-z0-9])', text) if alias.isascii() else alias in text)
        for alias in aliases)}


def subject_matches(query, text, context=''):
    required, body, heading = concepts(query), concepts(text), concepts(context)
    # Only identity can come from the displayed title/section. Capability terms
    # must occur in the original paragraph; metadata is never evidence of them.
    if not required <= body | (heading & IDENTITIES):
        return False
    for family in (COUNTRIES, COMPANIES, VEHICLES):
        wanted = required & family
        if wanted and body & family and not wanted <= body:
            return False
    wanted, found = mission_ids(query), mission_ids(text)
    return wanted <= (found or mission_ids(context))


def coverage(query, texts):
    required = concepts(query) | mission_ids(query)
    seen = set().union(*(concepts(t) | mission_ids(t) for t in texts)) if texts else set()
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

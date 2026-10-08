"""Explainable passage BM25 with exact, extraction-relative sentence spans."""
from collections import Counter
from dataclasses import asdict, is_dataclass
import math
import re
from functools import lru_cache
from research_search import keyword_tokens, SEARCH_STOP
from retrieval_constraints import subject_matches, GROUPS


TOKEN = re.compile(r'[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*|[\u3400-\u9fff]')
ABBREVIATIONS = {'mr.', 'mrs.', 'dr.', 'prof.', 'vs.', 'etc.', 'e.g.', 'i.e.', 'u.s.'}


@lru_cache(maxsize=32768)
def lexical(text):
    return frozenset(keyword_tokens(text))


def sentences(text, passage_id=''):
    start = 0
    spans = []
    for match in re.finditer(r'[.!?。？！；]+(?:["”’\)]*)', text):
        end = match.end()
        prefix = text[start:end].lower()
        if match.group().startswith('.') and (any(prefix.endswith(a) for a in ABBREVIATIONS)
                or (end < len(text) and text[end].isdigit())
                or (end < len(text) and not text[end].isspace() and text[end].isascii())):
            continue
        spans.append((start, end))
        start = end
    if start < len(text):
        spans.append((start, len(text)))
    result = []
    for a, b in spans:
        while a < b and text[a].isspace(): a += 1
        while b > a and text[b-1].isspace(): b -= 1
        if a < b:
            result.append({'sentence_id': f'{passage_id}:s{len(result)+1}',
                           'sentence_index': len(result)+1, 'text': text[a:b],
                           'character_start': a, 'character_end': b})
    return result


def match_details(text, query):
    terms = lexical(query)
    positions = []
    # Tokenize short spans so expansion provenance and highlight offsets remain exact.
    for i, m in enumerate(TOKEN.finditer(text)):
        end = m.end()
        if '\u3400' <= m.group()[0] <= '\u9fff':
            found = terms & {m.group(), text[m.start():m.start()+2]}
            if text[m.start():m.start()+2] in found: end = m.start()+2
            for canonical, aliases in GROUPS.items():
                for alias in aliases:
                    if canonical in terms and not alias.isascii() and text.startswith(alias,m.start()):
                        found = found | {canonical}; end = max(end,m.start()+len(alias))
        else:
            found = terms & lexical(m.group())
        if found: positions.append((i, m.start(), end, found))
    matched = terms & lexical(text)
    minimum = None
    counts, left = Counter(), 0
    for right, item in enumerate(positions):
        counts.update(item[3])
        while terms and terms <= {k for k, v in counts.items() if v}:
            width = item[0] - positions[left][0] + 1
            minimum = width if minimum is None else min(minimum, width)
            counts.subtract(positions[left][3]); left += 1
    phrases = re.findall(r'["“]([^"”]+)["”]', query)
    if not phrases:
        raw = [m.group().lower() for m in TOKEN.finditer(query) if m.group().lower() not in SEARCH_STOP]
        phrases = [' '.join(raw)] if len(raw) > 1 and not any('\u3400' <= c <= '\u9fff' for c in query) else []
        phrases += re.findall(r'[\u3400-\u9fff]{2,}', query)
    exact = [p for p in phrases if p.lower() in text.lower()]
    return {'matched_terms': sorted(matched), 'phrases': phrases, 'matched_phrases': exact,
            'term_coverage': len(matched)/len(terms) if terms else 0,
            'minimum_term_window': minimum,
            'highlight_spans': [[p[1], p[2]] for p in positions],
            'expansion_matches': [{'original':text[p[1]:p[2]], 'terms':sorted(p[3])} for p in positions
                                  if any(t != text[p[1]:p[2]].lower() for t in p[3])],
            'expanded_terms': sorted(matched - {m.group().lower() for m in TOKEN.finditer(text)})}


def rank_passages(passages, query, limit=5, per_document=2, deduplicate=True):
    q = set(keyword_tokens(query))
    if not q or not passages: return []
    vectors = [keyword_tokens(p['passage']) for p in passages]
    df = Counter(t for v in vectors for t in q if t in v)
    average = sum(sum(v.values()) for v in vectors)/len(vectors) or 1
    hits = []
    for p, v in zip(passages, vectors):
        text = p['passage']
        if not subject_matches(query, text): continue
        matched = q & v.keys()
        if not matched or (len(q) >= 3 and len(matched) < 2): continue
        length = sum(v.values())
        bm25 = sum(math.log(1+(len(vectors)-df[t]+.5)/(df[t]+.5))*v[t]*2.2/
                   (v[t]+1.2*(.25+.75*length/average)) for t in matched)
        details = match_details(text, query)
        ss = sentences(text, p['passage_id'])
        for s in ss: s['match'] = match_details(s['text'], query)
        best = max(ss, key=lambda s: (s['match']['term_coverage'], len(s['match']['matched_phrases']),
                                     -(s['match']['minimum_term_window'] or 100000)), default=None)
        same = bool(best and best['match']['term_coverage'] == 1)
        level = 'ALL_TERMS_SAME_SENTENCE' if same else 'ALL_TERMS_SAME_PARAGRAPH' if details['term_coverage'] == 1 else 'PARTIAL_PARAGRAPH'
        loc = p.get('location', {})
        loc = asdict(loc) if is_dataclass(loc) else loc
        fields = p.get('source', {}).get('title', '') + ' ' + (loc.get('section_heading') or '')
        field_boost = len(q & keyword_tokens(fields).keys())/len(q)
        score = bm25 * details['term_coverage']**2 * (1 + 2*same + len(details['matched_phrases'])
                + (2/(details['minimum_term_window'] or 100000)) + .2*field_boost)
        metadata = dict(details, match_level=level, retrieval_score=round(score, 8),
                        passage_id=p['passage_id'], best_sentence=best, location=loc)
        hits.append(dict(p, score=round(score, 8), retrieval_match=metadata))
    hits.sort(key=lambda p: (-p['score'], p['passage_id']))
    result, counts, seen = [], Counter(), set()
    for p in hits:
        doc = p['source']['id']
        normalized = ' '.join(p['passage'].lower().split())
        if counts[doc] >= per_document or (deduplicate and normalized in seen): continue
        counts[doc] += 1; seen.add(normalized); result.append(p)
        if len(result) >= limit: break
    return result

"""Transparent clause heuristics for retrieval relevance, never factual stance."""
from dataclasses import asdict, dataclass
from functools import lru_cache
import math
import re
import unicodedata

from domains.aerospace import retrieval_terms as terms
from retrieval_constraints import GROUPS, COUNTRIES, COMPANIES, VEHICLES, concepts


def norm(text):
    return unicodedata.normalize('NFKC', text).lower()


def pattern(alias):
    escaped = re.escape(alias)
    return r'(?<![a-z0-9])' + escaped + r'(?![a-z0-9])' if alias.isascii() else escaped


def contains(text, aliases):
    return any(re.search(pattern(a), text) for a in aliases)


def found(text, vocabulary):
    return {key for key, aliases in vocabulary.items() if contains(text, aliases)}


@lru_cache(maxsize=8192)
def normalize_variants(text):
    text = norm(text)
    replacements = [(alias, key) for key, aliases in terms.LEXICAL_VARIANTS.items() for alias in aliases]
    # Longest first; one pass avoids repeatedly expanding canonical terms.
    aliases = sorted(replacements, key=lambda pair: (-len(pair[0]), pair[0]))
    regex = '|'.join('(' + pattern(alias) + ')' for alias, _ in aliases)
    return re.sub(regex, lambda m: aliases[m.lastindex-1][1], text)


@dataclass(frozen=True)
class QueryIntent:
    entities: tuple = ()
    components: tuple = ()
    milestones: tuple = ()
    jurisdictions: tuple = ()
    temporal_terms: tuple = ()
    scope_terms: tuple = ()
    status_terms: tuple = ()
    negation: bool = False


def interpret(query):
    q = norm(query)
    components = found(q, terms.COMPONENTS)
    milestones = found(q, terms.MILESTONES)
    # Routine reuse is more specific than reuse; generic test is subordinate to
    # a specified restart/reflight. This does not turn one milestone into another.
    if 'routine' in milestones:
        milestones -= {'reuse', 'reflight', 'repeated_reflight'}
    elif 'repeated_reflight' in milestones:
        milestones -= {'reuse', 'reflight'}
    if milestones - {'test'}:
        milestones.discard('test')
    countries = concepts(q) & COUNTRIES
    known = concepts(q) & (COMPANIES | VEHICLES)
    entities = sorted(known)
    if not entities and (components or milestones):
        rest = re.sub(terms.QUERY_PREFIX, '', q)
        for key in countries:
            for alias in GROUPS[key]:
                rest = re.sub('^' + pattern(alias) + r'(?:的|\s)*', '', rest)
        boundaries = [m.start() for vocab in (terms.COMPONENTS, terms.MILESTONES)
                      for aliases in vocab.values() for alias in aliases
                      for m in re.finditer(pattern(alias), rest)]
        boundaries += [m.start() for m in re.finditer(terms.QUERY_BOUNDARY, rest)]
        entity = rest[:min(boundaries)] if boundaries else ''
        entity = re.sub(r'在(?:19|20)\d{2}年$', '', entity)
        entity = re.sub(r'\s+the\s*$', '', entity).strip(' 的-')
        # Unknown entity phrases are copied only from the query; never a roster
        # of synthetic names. Pronouns and generic query fragments abstain.
        if entity and entity not in ('it', '它', '该', 'the', 'a', 'an') and len(entity.split()) <= 5:
            entities = [entity]
    return QueryIntent(tuple(entities), tuple(sorted(components)), tuple(sorted(milestones)),
        tuple(sorted(countries)), tuple(re.findall(r'\b(?:19|20)\d{2}\b|(?<!\d)(?:19|20)\d{2}(?=年)', q)),
        ('both_stages',) if re.search(terms.SCOPE, q) else (),
        ('planned',) if re.search(terms.PLANNED, q) else ('completed',),
        bool(re.search(terms.NEGATIVE, q)))


def entity_present(text, entity):
    return contains(text, GROUPS.get(entity, (entity,)))


@lru_cache(maxsize=8192)
def clauses(text):
    # Do not split every "and": it commonly joins participants of one event.
    return tuple((c.strip(), index) for index, sentence in enumerate(re.split(r'[.!?。？！]', norm(text)))
                 for c in re.split(r'[；;，,:：]|\b(?:but|while|although)\b|但是|但|而', sentence) if c.strip())


def event_years(text):
    years = set(re.findall(r'\b(?:in|during|on)\s+((?:19|20)\d{2})(?!\s+(?:report|summary))', text))
    years.update(re.findall(r'在((?:19|20)\d{2})年(?!报告|报道)', text))
    return years


def event_components(clause):
    # A component's observers are not that component performing the event.
    for aliases in terms.COMPONENTS.values():
        for alias in aliases:
            clause = re.sub(pattern(alias) + r'(?:\s+(?:team|engineers|researchers)|团队)', '', clause)
    return found(clause, terms.COMPONENTS)


def feature_values(text, intent):
    text = norm(text)
    parts = clauses(text)
    requested = set(intent.milestones)
    components = set(intent.components)
    if intent.scope_terms:
        components = {'first_stage', 'upper_stage'}
    entity_match = not intent.entities or all(entity_present(text, e) for e in intent.entities)
    events = []
    preceding_entity, preceding_sentence = False, -1
    for clause, sentence in parts:
        milestones = found(clause, terms.MILESTONES)
        # An explicitly expendable/discarded component directly addresses reuse
        # capability, even without repeating the word "reuse".
        if 'reuse' in requested and re.search(r'\b(?:expendable|expends?|discarded)\b|一次性', clause):
            milestones.add('reuse')
        entities_here = not intent.entities or all(entity_present(clause, e) for e in intent.entities)
        inherited = not entities_here and preceding_entity and bool(re.match(
            r'^(?:its\b|it\b|the same\b|the recovered\b|expends?\b|其|该|回收后的)', clause))
        comp = event_components(clause)
        # Generic vehicle is not a requirement when a more specific component exists.
        required_comp = components - {'vehicle'} if components - {'vehicle'} else components
        component_match = not required_comp or (bool(required_comp & comp) if intent.scope_terms
                                                else required_comp <= comp)
        milestone_match = bool(requested & milestones)
        if 'routine' in requested:
            milestone_match = 'routine' in milestones
        planned = bool(re.search(terms.PLANNED, clause))
        completed = bool(re.search(terms.COMPLETED, clause))
        negative = bool(re.search(terms.NEGATIVE, clause))
        # Completion words inside a negated clause are not a positive event signal.
        completed = completed and not negative
        jurisdiction = concepts(clause) & COUNTRIES
        juris_conflict = bool(intent.jurisdictions and jurisdiction and not set(intent.jurisdictions) <= jurisdiction)
        if 'vehicle' in components and re.search(r'\blaboratory\b|实验室', clause):
            component_match = False
        years = event_years(clause) if entities_here or inherited else set()
        events.append({
            'entity_match': entity_match,
            'entity_event_locality': entities_here and milestone_match,
            'entity_sentence_locality': inherited and sentence == preceding_sentence,
            'entity_paragraph_locality': inherited and sentence != preceding_sentence,
            'entity_conflict': bool(intent.entities) and not (entities_here or inherited),
            'component_match': component_match,
            'component_conflict': bool(milestones and required_comp and comp and not component_match),
            'milestone_match': milestone_match,
            'milestone_conflict': bool(requested and not milestone_match),
            'completed_language': completed and milestone_match,
            'requested_completed': completed and milestone_match and intent.status_terms == ('completed',),
            'negative_answer': negative and milestone_match and component_match,
            'negation_present': negative,
            'planned_language': planned,
            'planned_when_completed_requested': planned and intent.status_terms == ('completed',),
            'requested_plan': planned and intent.status_terms == ('planned',),
            'background_language': bool(re.search(terms.BACKGROUND, clause)),
            'jurisdiction_match': bool(intent.jurisdictions) and set(intent.jurisdictions) <= jurisdiction,
            'jurisdiction_conflict': juris_conflict,
            'same_clause': entities_here and component_match and milestone_match,
            'temporal_match': bool(intent.temporal_terms and years) and set(intent.temporal_terms) <= years,
            'temporal_conflict': bool(intent.temporal_terms and years) and not set(intent.temporal_terms) <= years,
        })
        preceding_entity, preceding_sentence = entities_here or inherited, sentence
    if not events:
        return {'entity_match': entity_match, 'milestone_conflict': bool(requested)}
    # Select the strongest explicit event, not independent maxima from unrelated clauses.
    best = max(events, key=lambda f: sum(terms.WEIGHTS.get(k, 0)*v for k, v in f.items()))
    best['scope_components_present'] = not intent.scope_terms or {'first_stage','upper_stage'} <= event_components(text)
    return best


def rerank(candidates, query, *, strength=terms.RELATIONSHIP_STRENGTH):
    intent = interpret(query)
    if not intent.milestones:
        return candidates
    maximum = max((p['score'] for p in candidates), default=1) or 1
    result = []
    for p in candidates:
        features = feature_values(p['passage'], intent)
        relationship = sum(terms.WEIGHTS.get(k, 0)*value for k, value in features.items())
        # Positive monotonic transform keeps existing page-weighting consumers valid.
        score = 1 / (1 + math.exp(-(p['score']/maximum + strength*relationship)/4))
        category = ('CONFLICTING_ATTRIBUTE_MATCH' if any(features.get(k) for k in
                    ('entity_conflict','component_conflict','jurisdiction_conflict','temporal_conflict'))
                    else 'STRONG_RELATIONSHIP_MATCH' if features.get('same_clause') and
                    (features.get('completed_language') or features.get('negative_answer'))
                    else 'BACKGROUND_MATCH' if features.get('background_language')
                    else 'PARTIAL_RELATIONSHIP_MATCH')
        diagnostic = {'intent': asdict(intent), 'features': features, 'category': category,
                      'lexical_score': p['score'], 'relationship_score': relationship,
                      'requested_milestone_level': max((terms.MILESTONE_LEVEL.get(k, 0) for k in intent.milestones), default=0),
                      'reranked_score': round(score, 8)}
        result.append(dict(p, score=round(score, 8), retrieval_match=dict(p['retrieval_match'],
                      relationship=diagnostic, retrieval_score=round(score, 8))))
    return sorted(result, key=lambda p: (-p['score'], p['passage_id']))

"""Evidence-led, human-reviewed verification; lexical retrieval never proves a claim."""
from dataclasses import asdict
from copy import deepcopy
from difflib import SequenceMatcher
import re
from typing import Protocol
from urllib.parse import urlsplit
from research_search import search
from verification_models import AtomicClaim, EvidenceRecord, Verdict, STANCES, digest


class SearchProvider(Protocol):
    name: str
    def search(self, query: str) -> list[str]: ...


class ManualURLProvider:
    """Explicit sources only. This is not a current-web search engine."""
    name = 'manual_urls'
    def __init__(self, urls):
        self.urls = list(dict.fromkeys(urls))

    def search(self, query):
        return self.urls


def decompose(request, explicit=None):
    # Preserve wording; don't infer subjects across conjunctions.
    texts = explicit if explicit is not None else [x.strip() for x in re.split(r'[;；]\s*|\n+', request.text) if x.strip()]
    if not texts or len(texts) > 20 or any(not isinstance(t, str) or not t.strip() for t in texts):
        raise ValueError('Invalid atomic claims')
    return [AtomicClaim(f'c{i}', request.id, t, temporal_scope=request.requested_as_of_date)
            for i, t in enumerate(texts, 1)]


def query_intents(claim):
    return [{'intent': label, 'query': claim.text + suffix} for label, suffix in [
        ('primary_record', ' official technical report'), ('independent_reporting', ' independent confirmation'),
        ('newer_update', ' latest update correction'), ('contradictory_evidence', ' evidence disputed delayed')]]


def independence_groups(documents):
    parent = {d.source.source_id: d.source.source_id for d in documents}
    reasons = []
    def root(s):
        while parent[s] != s:
            s = parent[s]
        return s
    for i, a in enumerate(documents):
        for b in documents[i + 1:]:
            # Conservatively group same publisher, canonical copies, explicit links,
            # or near-duplicate documents. Never claim remaining groups independent.
            canonical_a = a.source.canonical_url or a.source.url
            canonical_b = b.source.canonical_url or b.source.url
            linked = b.source.url in a.source.attributed_to or a.source.url in b.source.attributed_to
            same_publisher = a.source.domain == b.source.domain
            duplicate = SequenceMatcher(None, a.text[:30000], b.text[:30000], autojunk=False).ratio() >= .85
            if same_publisher or canonical_a == canonical_b or linked or duplicate:
                parent[root(b.source.source_id)] = root(a.source.source_id)
                reasons.append({'source_ids': [a.source.source_id, b.source.source_id],
                                'reason': 'same publisher' if same_publisher else 'linked attribution' if linked else 'likely repeated text/canonical source'})
    return {sid: root(sid) for sid in parent}, reasons


def validate_citation(evidence, documents, claim_ids):
    docs = {d.source.source_id: d for d in documents}
    doc = docs.get(evidence.source_id)
    loc = evidence.location
    if not doc or evidence.claim_id not in claim_ids or not loc or not doc.source.allowed_as_evidence:
        return False
    if loc.source_id != evidence.source_id or not evidence.exact_passage or not doc.source.url.startswith('https://'):
        return False
    if not (0 <= loc.character_start < loc.character_end <= len(doc.text)):
        return False
    return any(p['location'] == loc and p['passage'] == evidence.exact_passage
               for p in doc.passages) and doc.text[loc.character_start:loc.character_end] == evidence.exact_passage


def candidates(claims, documents, limit=5):
    all_passages = [p for d in documents for p in d.passages]
    records = []
    for claim in claims:
        for p in search(all_passages, claim.text, limit):
            eid = digest(claim.claim_id + '\n' + claim.text + '\n' + p['passage_id'])[:24]
            records.append(EvidenceRecord(eid, claim.claim_id, p['source']['id'], p['passage'], p['location']))
    return records


def assess(request, claims, documents, evidence, reviews=None, failures=None, review_only=False):
    reviews = reviews or {}
    failures = list(failures or [])
    groups, dependencies = independence_groups(documents)
    sources = {d.source.source_id: d.source for d in documents}
    valid, accepted, temporal_exclusions, invalid_reviews = [], {}, [], []
    claim_ids = {c.claim_id for c in claims}
    for e in evidence:
        # Assessment is repeatable: caller-owned candidates and previous labels
        # must never become an implicit review on a subsequent run.
        e = deepcopy(e)
        e.stance, e.evidence_strength = 'CONTEXT', 'UNREVIEWED'
        e.normalized_passage, e.translation = None, None
        e.status, e.notes = 'UNKNOWN', []
        if not validate_citation(e, documents, claim_ids):
            failures.append('CITATION_VALIDATION_FAILED')
            continue
        e.source_independence_group = groups[e.source_id]
        source = sources[e.source_id]
        review = reviews.get(e.evidence_id)
        valid.append(e)
        if source.publication_date and source.publication_date > request.requested_as_of_date:
            temporal_exclusions.append(e.evidence_id)
            e.notes.append('Published after requested as-of date; excluded from assessment.')
            continue
        if not review:
            continue
        # Trusted review file is separate from fetched source content. Require an
        # auditable binding to claim, immutable document hash, and a reviewer.
        if (not isinstance(review, dict)
                or review.get('claim_id') != e.claim_id or review.get('document_hash') != source.content_hash
                or not review.get('reviewer') or not review.get('rationale')
                or review.get('stance') not in STANCES or review.get('relevant') is not True
                or review.get('strength') not in {'DIRECT', 'INDIRECT'}
                or review.get('basis') not in {'observation', 'announcement', 'attributed_report'}):
            invalid_reviews.append(e.evidence_id)
            continue
        e.stance, e.evidence_strength = review['stance'], review['strength']
        e.normalized_passage = review.get('normalized_fact')
        e.translation = review.get('translation')
        e.status = review.get('status', 'UNKNOWN')
        e.notes.append(review['rationale'])
        accepted[e.evidence_id] = review
    unknown_reviews = set(reviews) - {e.evidence_id for e in evidence}
    if invalid_reviews or unknown_reviews:
        failures.append('CITATION_VALIDATION_FAILED')
    # Explicit, reviewed supersession only; recency alone is not a correction.
    superseded = set()
    for e in valid:
        r = accepted.get(e.evidence_id, {})
        for old_id in r.get('supersedes', []):
            old = next((x for x in valid if x.evidence_id == old_id), None)
            newer_date = sources[e.source_id].publication_date
            older_date = sources[old.source_id].publication_date if old else None
            if (old and old.claim_id == e.claim_id and old_id in accepted
                    and newer_date and older_date and newer_date > older_date
                    and r.get('strength') == 'DIRECT' and r.get('material_scope_matches') is True
                    and r.get('basis') == 'observation' and sources[e.source_id].source_type != 'company'
                    and r.get('supersession_reason')):
                superseded.add(old_id)
    assessments = []
    for claim in claims:
        items = [e for e in valid if e.claim_id == claim.claim_id and e.evidence_id in accepted
                 and e.evidence_id not in superseded and e.evidence_id not in temporal_exclusions]
        support, contradict, qualify, excluded = [], [], [], []
        for e in items:
            r = accepted[e.evidence_id]
            # Unknown publication dates require an explicit reviewed temporal basis.
            usable = bool(sources[e.source_id].publication_date or r.get('temporal_basis'))
            usable &= r.get('material_scope_matches') is True and e.evidence_strength == 'DIRECT'
            # An announcement supports an announcement claim, not the underlying event.
            if (r['basis'] != 'observation' or sources[e.source_id].source_type == 'company'):
                usable &= r.get('claim_is_about_announcement') is True
            if request.domain == 'aerospace' and e.stance == 'SUPPORTS':
                from domains.aerospace.rules import capability_compatible
                usable &= capability_compatible(claim.text, e.status, r.get('milestone'))
            if not usable:
                excluded.append(e.evidence_id)
            elif e.stance == 'SUPPORTS': support.append(e.evidence_id)
            elif e.stance == 'CONTRADICTS': contradict.append(e.evidence_id)
            elif e.stance == 'QUALIFIES': qualify.append(e.evidence_id)
        verdict = Verdict.INSUFFICIENT.value
        if support and contradict:
            verdict = Verdict.MIXED.value
            failures.append('CONFLICT_UNRESOLVED')
        elif support:
            verdict = Verdict.MOSTLY_TRUE.value if qualify else Verdict.TRUE.value
        elif contradict:
            verdict = Verdict.FALSE.value
            if any(e.evidence_id in superseded and e.claim_id == claim.claim_id and e.stance == 'SUPPORTS' for e in valid):
                verdict = Verdict.OUTDATED.value
        assessments.append({'claim_id': claim.claim_id, 'verdict': verdict,
                            'supporting_evidence_ids': support, 'contradicting_evidence_ids': contradict,
                            'qualifying_evidence_ids': qualify, 'excluded_from_verdict': excluded})
    verdicts = {a['verdict'] for a in assessments}
    verdict = next(iter(verdicts)) if len(verdicts) == 1 else Verdict.MIXED.value
    if not any(a['supporting_evidence_ids'] or a['contradicting_evidence_ids'] for a in assessments):
        verdict = Verdict.INSUFFICIENT.value
        failures.append('INSUFFICIENT_EVIDENCE')
    sufficiency = ('INSUFFICIENT' if verdict == Verdict.INSUFFICIENT.value else
                   'PARTIAL' if failures or verdict in {Verdict.MIXED.value, Verdict.MOSTLY_TRUE.value} else 'SUFFICIENT')
    unresolved = [a['claim_id'] for a in assessments if a['verdict'] == Verdict.MIXED.value]
    return {'request': asdict(request), 'request_type': request.request_type,
            'as_of_date': request.requested_as_of_date, 'verdict': None if review_only else verdict,
            'evidence_sufficiency': sufficiency, 'review_only': review_only,
            'short_answer': 'Evidence is awaiting human review.' if review_only else
                'The supplied reviewed evidence does not establish an answer.' if verdict == Verdict.INSUFFICIENT.value else
                'Reviewed evidence assessment: ' + verdict.replace('_', ' ').lower() + '.',
            'explanation': 'This result is limited to the retrieved documents and explicit human assessments. '
                           'Lexical matches, official attribution, and repeated reporting are not independent proof.',
            'atomic_claims': [asdict(c) for c in claims], 'assessments': [] if review_only else assessments,
            'key_evidence': [asdict(e) for e in valid], 'sources': [asdict(d.source) for d in documents],
            'source_differences': {'likely_dependencies': dependencies, 'unresolved_conflicts': unresolved,
                                   'superseded_evidence_ids': sorted(superseded),
                                   'future_evidence_ids': temporal_exclusions},
            'uncertainties': ['Unlinked sources are not proven independent.',
                              'Semantic relevance, scope and stance require human review.',
                              'Missing public evidence is not proof that an event did not occur.'],
            'failures': sorted(set(failures)), 'invalid_review_ids': sorted(set(invalid_reviews) | unknown_reviews),
            'reviews': reviews}


def markdown(result):
    # No long quotations; exact passages remain in the private JSON audit record.
    q = result['request_type'] == 'QUESTION'
    safe = lambda t: re.sub(r'([\\`*_{}\[\]<>#!])', r'\\\1', str(t)).replace('\n', ' ')
    lines = ['# ' + ('Answer' if q else 'Verification'), '',
             result['short_answer'] if q or result['review_only'] else '**' + result['verdict'] + '**', '',
             'As of ' + result['as_of_date'] + '. ' + result['explanation'], '',
             'Scope: ' + result.get('research_scope', 'supplied documents only'), '', '## What the evidence supports', '']
    claim_text = {c['claim_id']: c['text'] for c in result['atomic_claims']}
    for a in result['assessments']:
        lines.append('- ' + safe(claim_text[a['claim_id']]) + ': ' + a['verdict'])
    lines += ['', '## Evidence', '']
    sources = {s['source_id']: s for s in result['sources']}
    for e in result['key_evidence']:
        s, loc = sources[e['source_id']], e['location']
        where = (f"PDF page {loc['page_number']}, " if loc['page_number'] else '')
        where += f"extracted paragraph {loc['paragraph_index']}"
        if loc['section_heading']:
            where += ', section ' + loc['section_heading'][:100].replace('\n', ' ')
        # Titles/headings are untrusted plain text, not Markdown directives.
        lines += [f"- {safe(s['publisher'])} — {safe(s['title'])} ({s['publication_date'] or 'date unknown'}). "
                  f"{e['stance']}; {safe(where)}. [Source]({s['url'].replace(')', '%29').replace('(', '%28')})."]
        if e['normalized_passage']:
            lines.append('  Reviewed interpretation: ' + safe(e['normalized_passage'][:400]))
    lines += ['', '## Where sources differ', '',
              'Unresolved claim conflicts: ' + (', '.join(result['source_differences']['unresolved_conflicts']) or 'none established'),
              'Likely dependency relationships: ' + str(len(result['source_differences']['likely_dependencies'])),
              '', '## Remaining uncertainty', ''] + ['- ' + x for x in result['uncertainties']]
    lines += ['', 'Failure states: ' + (', '.join(result['failures']) or 'none')]
    return '\n'.join(lines) + '\n'

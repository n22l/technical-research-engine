"""Local UI application service; all factual judgments stay in the engine."""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import threading
import uuid
from copy import deepcopy

from research_search import private_directory, external_directory, safe_file, private_output, SafeError
from verification_models import ResearchRequest, digest, now, STANCES
from verification import decompose, candidates, assess, markdown
from verify import research
from search_discovery import configured_provider, SearchError
from web_sources import SourcePolicy, parse_document
from domains.aerospace.rules import STATUSES, MILESTONES
import source_suggestions

ROOT = Path(__file__).resolve().parent


class UIError(ValueError):
    pass


class Application:
    def __init__(self, base=None, policy=None):
        self.base = external_directory(base) if base is not None else private_directory()
        self.policy = policy or SourcePolicy.load(ROOT.parent / 'config/source-policy.json')
        self.lock = threading.RLock()
        for suggestion in source_suggestions.suggestions(self.base):
            if suggestion['status'] == 'approved' and suggestion['host'] not in self.policy.rules:
                self.policy.rules[suggestion['host']] = source_suggestions.approved_rule(suggestion)
        self.jobs = {}
        self.busy = False

    def configuration(self):
        return {'configured': True, 'providers': {'local': True,
                'brave': bool(os.environ.get('BRAVE_SEARCH_API_KEY')),
                'searxng': bool(os.environ.get('TECH_RESEARCH_SEARXNG_URL'))},
                'sources': [{'host': host, **rule} for host, rule in self.policy.rules.items()],
                'statuses': sorted(STATUSES), 'milestones': list(MILESTONES)}

    def source_suggestions(self):
        with self.lock:
            return source_suggestions.suggestions(self.base)

    def suggest_source(self, values):
        with self.lock:
            try:
                return source_suggestions.submit(self.base, self.policy, values)
            except ValueError as exc:
                raise UIError(str(exc)) from None

    def decide_source(self, values):
        with self.lock:
            if self.busy:
                raise UIError('Wait for the active research job before changing approved sources.')
            try:
                return source_suggestions.decide(self.base, self.policy, values)
            except ValueError as exc:
                raise UIError(str(exc)) from None

    def _history(self):
        latest = {}
        for path in self.base.glob('result-*.json'):
            if not re.fullmatch(r'result-[0-9a-f]{32}\.json', path.name):
                continue
            try:
                path = safe_file(self.base, path.name)
                if path.stat().st_size > 20_000_000:
                    continue
                data = json.loads(path.read_text(encoding='utf-8'))
                if data.get('ui_schema') != 1 or not re.fullmatch(r'[0-9a-f]{32}', data.get('id', '')):
                    continue
                if data['id'] not in latest or data['revision'] > latest[data['id']]['revision']:
                    latest[data['id']] = data
            except (ValueError, OSError, KeyError, TypeError, SafeError):
                continue
        return latest

    def history(self):
        with self.lock:
            return [{'id': r['id'], 'date': r['updated'], 'text': r['result']['request']['text'],
                     'status': 'Verified' if r.get('final') else 'Awaiting review',
                     'verdict': (r.get('final') or {}).get('verdict'),
                     'provider': r['result']['search']['provider']}
                    for r in sorted(self._history().values(), key=lambda r: r['updated'], reverse=True)]

    def load(self, run_id):
        if not re.fullmatch(r'[0-9a-f]{32}', run_id):
            raise UIError('Unknown research run.')
        state = self._history().get(run_id)
        if state is None:
            raise UIError('Unknown research run.')
        return state

    def _save(self, state):
        state['revision'] += 1
        state['updated'] = now()
        private_output(self.base, state)

    def view(self, run_id):
        with self.lock:
            state = deepcopy(self.load(run_id))
            try:
                self._documents(state)
                state['integrity_error'] = None
            except UIError as exc:
                state['integrity_error'] = str(exc)
                state['final'] = None
        # Never expose captures, filenames, raw search snippets or instance URLs.
        r = state['result']
        search = r['search']
        local = search.get('local_index', {})
        summary = {'queries': len(search['queries_issued']), 'candidates': len(search['candidates']),
                   'approved': sum(c['source_policy_status'] == 'APPROVED_EVIDENCE_SOURCE' for c in search['candidates']),
                   'parsed': len(r['sources']), 'evidence': len(r['key_evidence']),
                   'provider': search['provider'], 'status': search['status'],
                   'indexed_at': local.get('indexed_at'), 'indexed_pages': local.get('indexed_pages'),
                   'cache_used': local.get('cache_used'), 'pending_urls': local.get('pending_urls', 0),
                   'stale_pages': local.get('stale_pages', 0), 'index_hosts': local.get('hosts', []),
                   'hosts': sorted({s['domain'] for s in r['sources']})}
        parsed_urls = {source['url'] for source in r['sources']}
        events = r.get('run_manifest', {}).get('events', [])
        summary['unparsed_sources'] = []
        for url in search['selected_urls']:
            if url in parsed_urls:
                continue
            rule = self.policy.qualify(url)
            failed = next((event['stage'] for event in reversed(events)
                           if event.get('url') == url and event.get('status') == 'failed'), None)
            summary['unparsed_sources'].append({
                'url': url, 'publisher': rule.get('publisher') or 'Unknown publisher',
                'source_tier': rule.get('tier'), 'source_type': rule.get('type', 'unknown'),
                'status': 'Parsing failed' if failed == 'parse' else 'Retrieval unavailable',
            })
        r.pop('run_manifest', None)
        r['search'] = summary
        for record in [r, state.get('final')]:
            if record:
                record.pop('run_manifest', None)
                record.pop('reviews', None)
                if record is not r:
                    record.pop('search', None)
                for e in record['key_evidence']:
                    e['passage_truncated'] = len(e['exact_passage']) > 1200
                    e['exact_passage'] = e['exact_passage'][:1200]
        state['can_verify'] = (self._ready(state) and not state['integrity_error']
                               and search['status'] != 'SEARCH_FAILED')
        return state

    def start(self, values):
        if not isinstance(values, dict):
            raise UIError('Invalid request.')
        text = values.get('text', '')
        if not isinstance(text, str) or not text.strip() or len(text) > 10000:
            raise UIError('Enter a question or statement (up to 10,000 characters).')
        domain = values.get('domain') or None
        language = values.get('language', 'en')
        if domain not in (None, 'aerospace') or language not in ('en', 'zh'):
            raise UIError('Choose a supported domain and language.')
        try:
            request = ResearchRequest(text, values.get('request_type', 'AUTO'), domain=domain,
                                      language=language, **({'requested_as_of_date': values['as_of']} if values.get('as_of') else {}))
        except (ValueError, TypeError):
            raise UIError('Check the request type and as-of date.') from None
        provider_name = values.get('provider', 'local')
        if provider_name not in ('local', 'manual', 'brave', 'searxng'):
            raise UIError('Unknown search provider.')
        # Old browser tabs may still submit the former manual option.
        # UI research always discovers approved sources unless another provider is explicit.
        if provider_name == 'manual':
            provider_name = 'local'
        urls = values.get('urls', [])
        if not isinstance(urls, list) or len(urls) > 20 or any(not isinstance(u, str) or len(u) > 4096 for u in urls):
            raise UIError('Provide at most 20 source URLs.')
        with self.lock:
            if self.busy:
                raise UIError('A research job is already running. Please wait.')
            if len(self.jobs) >= 100:
                self.jobs = {k: v for k, v in self.jobs.items() if v['status'] == 'running'}
            job_id = uuid.uuid4().hex
            self.jobs[job_id] = {'status': 'running', 'stage': 'Preparing research…'}
            self.busy = True
        threading.Thread(target=self._research, args=(job_id, request, provider_name, urls, values.get('refresh') is True), daemon=True).start()
        return {'job_id': job_id}

    def _research(self, job_id, request, provider_name, urls, refresh):
        try:
            provider, error = None, None
            try:
                provider = configured_provider(provider_name, base=self.base, policy=self.policy, refresh=refresh)
            except SearchError as exc:
                error = exc.code
            with self.lock:
                self.jobs[job_id]['stage'] = 'Discovering sources, fetching documents and extracting evidence…'
            result = research(request, self.policy, urls, self.base, search_provider=provider,
                              review_only=True, automatic=provider_name != 'manual', configuration_error=error)
            state = {'ui_schema': 1, 'id': uuid.uuid4().hex, 'revision': 0, 'updated': now(),
                     'result': result, 'reviews': {}, 'final': None}
            with self.lock:
                self._save(state)
                self.jobs[job_id] = {'status': 'complete', 'run_id': state['id']}
        except Exception:
            with self.lock:
                self.jobs[job_id] = {'status': 'failed', 'error': 'Research could not finish. Check private storage and provider configuration.'}
        finally:
            with self.lock:
                self.busy = False

    def job(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                raise UIError('Unknown job. Open History to recover completed research.')
            return dict(self.jobs[job_id])

    def _documents(self, state):
        r = state['result']
        captures = {c['url']: c for c in r['run_manifest']['captures']}
        docs = []
        try:
            for source in r['sources']:
                capture = captures[source['url']]
                path = safe_file(self.base, capture['file'])
                if path.stat().st_size > 4_000_000:
                    raise ValueError('size')
                body = path.read_bytes()
                if digest(body) != source['content_hash']:
                    raise ValueError('changed')
                with contextlib.redirect_stderr(io.StringIO()):
                    doc = parse_document(source['url'], body, capture['media_type'], self.policy)
                if doc.source.source_id != source['source_id']:
                    raise ValueError('changed')
                docs.append(doc)
        except Exception:
            raise UIError('This source changed or is unavailable since research. Please research and review this evidence again.') from None
        return docs

    def save_review(self, run_id, values):
        with self.lock:
            state = self.load(run_id)
            if values.get('revision') != state['revision']:
                raise UIError('This run changed in another tab. Reopen it before saving.')
            self._documents(state)
            e = next((e for e in state['result']['key_evidence'] if e['evidence_id'] == values.get('evidence_id')), None)
            if not e:
                raise UIError('Unknown evidence.')
            relevant = values.get('relevant')
            if type(relevant) is not bool:
                raise UIError('Choose whether the evidence is relevant.')
            review = {'relevant': relevant}
            if relevant:
                for key, allowed in [('stance', STANCES), ('strength', {'DIRECT', 'INDIRECT'}),
                                     ('basis', {'observation', 'announcement', 'attributed_report'}),
                                     ('status', STATUSES), ('milestone', set(MILESTONES) | {''})]:
                    if values.get(key) not in allowed:
                        raise UIError('Complete the evidence assessment fields.')
                    review[key] = values[key]
                for key in ('reviewer', 'rationale', 'normalized_fact', 'translation', 'temporal_basis'):
                    value = values.get(key, '')
                    if not isinstance(value, str) or len(value) > 2000:
                        raise UIError('Review text must be under 2,000 characters per field.')
                    review[key] = value.strip()
                if not review['reviewer'] or not review['rationale']:
                    raise UIError('Reviewer name and rationale are required for relevant evidence.')
                review['material_scope_matches'] = values.get('material_scope_matches') is True
                review['claim_is_about_announcement'] = values.get('claim_is_about_announcement') is True
            source = next(s for s in state['result']['sources'] if s['source_id'] == e['source_id'])
            review.update(claim_id=e['claim_id'], document_hash=source['content_hash'])
            state['reviews'][e['evidence_id']] = review
            state['final'] = None
            self._save(state)
        return self.view(run_id)

    def _ready(self, state):
        ids = {e['evidence_id'] for e in state['result']['key_evidence']}
        return bool(ids and ids <= state['reviews'].keys() and
                    any(r.get('relevant') for r in state['reviews'].values()))

    def verify(self, run_id, revision):
        with self.lock:
            state = self.load(run_id)
            if revision != state['revision'] or not self._ready(state):
                raise UIError('Review every candidate and mark at least one relevant before verification.')
            original = state['result']
            if (original['search']['status'] == 'SEARCH_FAILED' or
                    (original['search']['provider'] != 'manual_urls' and original['search']['status'] != 'SEARCH_COMPLETE')):
                raise UIError('Search failed. Repeat research successfully before verification.')
            docs = self._documents(state)
            request = ResearchRequest(**original['request'])
            claims = decompose(request, [c['text'] for c in original['atomic_claims']])
            evidence = candidates(claims, docs)
            if {e.evidence_id for e in evidence} != {e['evidence_id'] for e in original['key_evidence']}:
                raise UIError('Evidence changed. Research and review again.')
            reviews = {k: v for k, v in state['reviews'].items() if v.get('relevant')}
            result = assess(request, claims, docs, evidence, reviews,
                            [f for f in original['failures'] if f != 'INSUFFICIENT_EVIDENCE'])
            if result['invalid_review_ids'] or 'CITATION_VALIDATION_FAILED' in result['failures']:
                raise UIError('Review or citation validation failed. Research and review again.')
            result.update(research_scope=original['research_scope'], search=original['search'], run_manifest=original['run_manifest'])
            state['final'] = result
            self._save(state)
        return self.view(run_id)

    def export(self, run_id, format):
        with self.lock:
            state = self.load(run_id)
            if not state.get('final'):
                raise UIError('Verify the reviewed evidence before exporting a final report.')
            self._documents(state)
            result = state['final']
            return markdown(result) if format == 'markdown' else json.dumps(result, ensure_ascii=False, indent=2)

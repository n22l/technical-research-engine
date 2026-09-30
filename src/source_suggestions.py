"""Private, explicit approval workflow for additional exact-host sources."""
import ipaddress
import json
import re
import uuid
from urllib.parse import urlsplit
from research_search import safe_file, private_output, SafeError
from search_discovery import normalize_url
from verification_models import now

TYPES = {'government', 'regulator', 'research_organization', 'company', 'major_news'}


def source_fields(values):
    url = normalize_url(values.get('url', ''))
    host = urlsplit(url).hostname
    if '.' not in host or host.endswith(('.local', '.internal', '.localhost')):
        raise ValueError('Use a public HTTPS source website.')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        raise ValueError('Use a public website hostname, not an IP address.')
    publisher, reason = values.get('publisher', ''), values.get('reason', '')
    if not all(isinstance(s, str) and s.strip() and len(s) <= 1000 for s in (publisher, reason)):
        raise ValueError('Publisher and reason are required (up to 1,000 characters).')
    return dict(url=url, host=host, publisher=publisher.strip(), reason=reason.strip())


def suggestions(base):
    latest = {}
    for path in base.glob('result-*.json'):
        if not re.fullmatch(r'result-[0-9a-f]{32}\.json', path.name):
            continue
        try:
            path = safe_file(base, path.name)
            if path.stat().st_size > 10000:
                continue
            row = json.loads(path.read_text(encoding='utf-8'))
            if row.get('source_suggestion_schema') != 1:
                continue
            if not re.fullmatch('[0-9a-f]{32}', row['id']):
                continue
            fields = source_fields(row)
            if fields['host'] != row['host'] or row['status'] not in ('pending', 'approved', 'rejected'):
                continue
            if row['status'] == 'approved' and (row.get('type') not in TYPES or row.get('tier') not in (1, 2)
                    or not row.get('reviewer') or row.get('confirmed') is not True):
                continue
            if row['id'] not in latest or row['revision'] > latest[row['id']]['revision']:
                latest[row['id']] = row
        except (ValueError, TypeError, KeyError, OSError, SafeError):
            continue
    return sorted(latest.values(), key=lambda r: r['updated'], reverse=True)


def approved_rule(row):
    return {'allowed': True, 'publisher': row['publisher'], 'tier': row['tier'], 'type': row['type'],
            'official': row.get('official') is True, 'primary': row.get('official') is True,
            'crawl_seeds': [row['url']]}


def submit(base, policy, values):
    fields = source_fields(values)
    if fields['host'] in policy.rules:
        raise ValueError('This host is already in the source policy.')
    if any(r['host'] == fields['host'] and r['status'] == 'pending' for r in suggestions(base)):
        raise ValueError('This host already has a pending suggestion.')
    row = dict(fields, source_suggestion_schema=1, id=uuid.uuid4().hex, status='pending', revision=1, updated=now())
    private_output(base, row)
    return row


def decide(base, policy, values):
    row = next((r for r in suggestions(base) if r['id'] == values.get('id')), None)
    if not row or row['status'] != 'pending':
        raise ValueError('This suggestion is no longer pending. Refresh the Sources page.')
    if values.get('decision') not in ('approve', 'reject'):
        raise ValueError('Choose approve or reject.')
    if values['decision'] == 'approve':
        if values.get('confirmed') is not True:
            raise ValueError('Confirm that you reviewed the website before approving.')
        reviewer = values.get('reviewer', '')
        if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 200:
            raise ValueError('Enter the approving reviewer name.')
        if values.get('type') not in TYPES or type(values.get('tier')) is not int or values['tier'] not in (1, 2):
            raise ValueError('Choose the source classification and tier.')
        if row['host'] in policy.rules:
            raise ValueError('This host is already configured; existing policy cannot be overwritten here.')
        row.update(status='approved', reviewer=reviewer.strip(), confirmed=True,
                   type=values['type'], tier=values['tier'], official=values.get('official') is True)
    else:
        row['status'] = 'rejected'
    row.update(revision=2, updated=now())
    private_output(base, row)
    if row['status'] == 'approved':
        policy.rules[row['host']] = approved_rule(row)
    return row

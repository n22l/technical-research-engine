"""Small explicit contracts; source text is evidence, never executable instructions."""
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timezone
from enum import Enum
import hashlib
import uuid


class Verdict(str, Enum):
    TRUE = 'TRUE'
    MOSTLY_TRUE = 'MOSTLY_TRUE'
    MIXED = 'MIXED_OR_CONTEXT_DEPENDENT'
    MOSTLY_FALSE = 'MOSTLY_FALSE'
    FALSE = 'FALSE'
    INSUFFICIENT = 'INSUFFICIENT_PUBLIC_EVIDENCE'
    OUTDATED = 'OUTDATED'


STANCES = {'SUPPORTS', 'CONTRADICTS', 'QUALIFIES', 'CONTEXT', 'INCONCLUSIVE'}
FAILURES = {'SEARCH_UNAVAILABLE', 'FETCH_FAILED', 'SOURCE_NOT_ALLOWED',
            'PARSE_FAILED', 'INSUFFICIENT_EVIDENCE', 'CITATION_VALIDATION_FAILED',
            'CONFLICT_UNRESOLVED'}


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode('utf-8')).hexdigest()


@dataclass
class ResearchRequest:
    text: str
    request_type: str = 'AUTO'
    requested_as_of_date: str = field(default_factory=lambda: date.today().isoformat())
    language: str = 'en'
    domain: str | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=now)

    def __post_init__(self):
        if not self.text.strip() or len(self.text) > 10000:
            raise ValueError('Invalid request')
        date.fromisoformat(self.requested_as_of_date)
        if self.request_type not in {'QUESTION', 'CLAIM', 'COMPARISON', 'AUTO'}:
            raise ValueError('Invalid request type')
        if self.request_type == 'AUTO':
            self.request_type = 'QUESTION' if self.text.rstrip().endswith(('?', '？')) else 'CLAIM'


@dataclass
class AtomicClaim:
    claim_id: str
    parent_request_id: str
    text: str
    qualifiers: list = field(default_factory=list)
    temporal_scope: str | None = None
    geographic_scope: str | None = None


@dataclass
class SourceRecord:
    source_id: str
    url: str
    canonical_url: str | None
    title: str
    publisher: str
    publication_date: str | None
    retrieval_date: str
    source_tier: int | None
    source_type: str
    language: str
    domain: str
    allowed_as_evidence: bool
    content_hash: str
    event_date: str | None = None
    author: str | None = None
    jurisdiction: str | None = None
    official: bool = False
    primary_source: bool = False
    attributed_to: list = field(default_factory=list)


@dataclass
class EvidenceLocation:
    source_id: str
    paragraph_index: int
    paragraph_start_text: str
    character_start: int
    character_end: int
    page_number: int | None = None
    section_heading: str | None = None
    locator_basis: str = 'extracted document; not website numbering'


@dataclass
class Document:
    source: SourceRecord
    text: str
    passages: list


@dataclass
class EvidenceRecord:
    evidence_id: str
    claim_id: str
    source_id: str
    exact_passage: str
    location: EvidenceLocation
    normalized_passage: str | None = None
    translation: str | None = None
    stance: str = 'CONTEXT'
    evidence_strength: str = 'UNREVIEWED'
    source_independence_group: str | None = None
    status: str = 'UNKNOWN'
    notes: list = field(default_factory=list)


def to_dict(record):
    return asdict(record)

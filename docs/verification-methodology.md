# Verification contract

The question is what retrieved, reviewed evidence supports. Lexical relevance is only a candidate, not a fact.

AUTO recognizes final question marks; other inputs default to CLAIM. Automatic decomposition splits semicolons/newlines without inventing pronoun bindings. Supply `atomic_claims` for compound statements; human reviewers must check coverage. COMPARISON uses the same pipeline.

Four bounded query intents seek primary records, independent reporting, corrections and contradiction. They remain unissued: only manual URLs are implemented. Online runs explicitly flag search unavailable. Snippets never enter the evidence path. Approved manual URLs fetch actual pages; offline mode reads explicit private captures.

## Private bundle

Store UTF-8 JSON outside every Git tree:

```json
{
  "text": "Test booster has routine reuse.",
  "atomic_claims": ["Test booster has routine reuse."],
  "urls": ["https://agency.example/report"],
  "captures": {
    "https://agency.example/report": {"file": "capture-fixture.bin", "media_type": "text/html"}
  },
  "reviews": {}
}
```

These values are synthetic. Default policy does not approve `.example`; an offline exercise needs an explicit private `--policy policy.json`. Real research uses actual qualified hosts. Review-only returns claims, evidence IDs, original passages, locations and hashes, without a verdict. Its capture manifest can populate an offline bundle.

Each review is keyed by evidence ID and requires `claim_id`, `document_hash`, nonempty `reviewer` and `rationale`, `relevant: true`, `stance` (SUPPORTS/CONTRADICTS/QUALIFIES/CONTEXT/INCONCLUSIVE), `strength` (DIRECT/INDIRECT), and `basis` (observation/announcement/attributed_report). Verdict eligibility also requires `material_scope_matches: true`. Unknown publication dates need a reviewed `temporal_basis`.

Optional review fields: `normalized_fact`, `translation`, `status`, `milestone`, `claim_is_about_announcement`, `supersedes` (evidence IDs), `supersession_reason`. Human reviews are trusted input and can be wrong. Page content cannot supply them. Citation validation proves location integrity; relevance/entailment remain human judgments. Reuse the same captures, request and claims for stable evidence IDs.

## Assessment

Only direct, relevant, materially scope-matching reviewed evidence affects verdicts. Company sources and attributed/announcement evidence support announcement claims only with explicit reviewer confirmation of that scope. Aerospace support for reuse additionally requires demonstrated/operational status and the corresponding milestone. Contradicting evidence need not demonstrate a capability.

Future publications are excluded by as-of date. Supersession requires an explicit reviewed same-claim relationship, newer dated source and reason; recency alone is insufficient. Event dates are representable but not extracted automatically. Reviewers must check temporal scope.

Same publishers, canonical copies, explicit links and near-duplicates are grouped as likely dependencies. Unlinked groups are not proven independent. Supporting and contradicting material evidence remains an unresolved conflict. No support yields insufficiency, not a guessed negative. Failures are separately reported, never converted into FALSE.

| Verdict | Definition |
| --- | --- |
| TRUE | Direct reviewed evidence supports the material claim. |
| MOSTLY_TRUE | Support exists with material qualifications. |
| MIXED_OR_CONTEXT_DEPENDENT | Subclaims differ or direct support and contradiction remain unresolved. |
| MOSTLY_FALSE | Some content is correct but the central implication is wrong; represented but not automatically assigned in this slice. |
| FALSE | Direct reviewed evidence contradicts the material claim. |
| INSUFFICIENT_PUBLIC_EVIDENCE | Retrieved approved evidence cannot establish the claim; not proof of absence in reality. |
| OUTDATED | A reviewed newer correction supersedes previous supporting evidence. |

Sufficiency (SUFFICIENT/PARTIAL/INSUFFICIENT) is separate and limited to this run. No numeric confidence is invented. Questions render as answers; current main text is templated, not synthesized domain prose.

Reports preserve source text, normalized fact, interpretation and verdict separately. Private manifests contain request/as-of, policy/limits, hashes, retrieval times, planned versus issued queries, evidence IDs, reviews, events and engine version. Captures are created exclusively externally. Error states include SEARCH_UNAVAILABLE, FETCH_FAILED, SOURCE_NOT_ALLOWED, PARSE_FAILED, INSUFFICIENT_EVIDENCE, CITATION_VALIDATION_FAILED and CONFLICT_UNRESOLVED. No secrets or full source text enter event logs; exact passages are intentionally retained in private evidence records.

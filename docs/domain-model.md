> Scope: this document describes the preserved local retrieval contract. New verification records and the opt-in aerospace runtime guard are defined in verification-methodology.md and citation-model.md.

# Domain model

## Current pattern

```text
Core engine: prepared-text ingestion, lexical retrieval, labeled retrieval evaluation
    ↓ source metadata (optional domain label)
Domain guidance: Aerospace Intelligence
    ↓ proposed entities and milestone taxonomy for human annotation
```

The runtime does not load domain configuration, classify statuses, or extract entities. Its generic metadata contract is the extension point today. A future domain configuration can select schemas, entity conventions, and taxonomies without requiring the core to adopt one domain's categories. Build that loader only when a working evidence feature needs it.

## Implemented document metadata

| Field | Current behavior |
| --- | --- |
| `id` | Required unique ASCII identifier; current equivalent of conceptual `document_id`. Preserve this key for existing manifests. |
| `title`, `publisher` | Required nonempty source metadata strings; do not invent missing facts. |
| `source_url` | Required HTTP(S) reference, or `synthetic:` for invented fixtures; never fetched. |
| `publication_date` | Required ISO date or explicit `unknown`. |
| `language` | Required language tag with 2–8 ASCII letters followed by optional hyphen-separated 1–8-character alphanumeric subtags. Syntax check only, not full BCP 47 validation. |
| `domain` | Optional nonempty string, preserved verbatim; no default, inference, fixed enum, or filtering. |
| `file` | Required local relative UTF-8 text path; validated but excluded from returned source metadata. |

Omitting `domain` preserves the old output shape. No metadata is fabricated. Unknown additional keys are not currently carried into passage results. Existing `en` and `zh` manifests still work; tags such as `zh-Hans` are accepted. Metadata tests using another tag do not evaluate that language's retrieval. Only English/Chinese retrieval is smoke-tested, and no broad multilingual performance is established.

Passages contain `passage_id`, `passage`, `source`, and `paragraph`; search adds a cosine `score`. Paragraph IDs remain stable only while document IDs and paragraph boundaries remain unchanged. Results are retrieved passages, not verified evidence records.

## Planned metadata and evidence records

The larger document model may include `document_id`, title, publisher, source URL, publication date, retrieval date, language, domain, source type, `jurisdiction_or_system`, and `copyright_or_license_notes`, together with version/hash and parsing notes. Fields beyond the table above are planning guidance, not an implemented schema. Never replace unknown values with invented metadata.

Planned evidence records would link reviewed original passages to scoped claims, supporting/conflicting evidence, review status, as-of dates, and explained uncertainty. Source reliability, human verification, and milestone status are separate judgments.

## Domain 01: Aerospace Intelligence

The only concrete application is [Aerospace Intelligence](../src/domains/aerospace/README.md). Relevant concepts include launch vehicles, launch sites, missions, payloads, recovery, reuse, orbital systems, government agencies, commercial providers, launch cadence, and demonstrated versus planned capability. These concepts are domain guidance, not implemented extraction classes.

The [aerospace taxonomy](../src/domains/aerospace/taxonomy.md) retains DEMONSTRATED, OPERATIONAL, TESTING, PLANNED, TARGETED, PROPOSED, DELAYED, CANCELLED, and UNKNOWN. It is neither mandatory for other domains nor automatically assigned today. Additional domains remain planned and unevaluated; do not invent integrations to demonstrate generality.

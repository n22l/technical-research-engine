> Runtime update: configurable qualification is now implemented; see source-policy.md for exact host rules and verification-methodology.md for claim-specific review. The curation principles below continue to apply.

# Data-source policy

**Status: Source policy for future real-corpus work.** The runnable demo includes only clearly labeled synthetic fixtures; no real source collection is included. All production documents, source metadata, indexes, and outputs must remain outside the repository in an explicitly configured non-Git directory. See the [local guide](local-retrieval.md).

## Source priorities

1. Primary official sources: government agencies, regulators, original technical records, program documentation, and attributable organization/company statements.
2. Authoritative technical publications with clear authorship, methods, dates, and references.
3. High-quality secondary reporting when necessary to fill gaps or identify primary material.

Aerospace-specific candidates and scope are documented under [Domain 01](../src/domains/aerospace/README.md). Other technical domains have not been implemented or evaluated.

Prefer original-language documents over unattributed translations and reposts. Preserve provenance when a document is republished. Official and corporate sources establish attributable statements but may not independently substantiate performance or economic claims.

## First application: aerospace corpus boundaries

The first corpus should be deliberately small and manually curated around reusable rockets, launch cadence, operational reuse, and publicly documented economic factors. Before collection, choose a date range, system coverage, language balance, and supported document formats.

Include documents because they address defined research questions. Record exclusions and gaps to make selection bias visible. Do not infer profitability from cadence alone, or equate launch price with internal cost.

## Metadata principles

The [domain model](domain-model.md) specifies the implemented subset. The table below is broader collection guidance; most additional fields are planned and are not preserved by the current result schema.

| Field | Convention |
| --- | --- |
| Title | Original title; translated title may be stored separately. |
| URL | Canonical source URL, with version/archive information where available and permitted. |
| Publisher | Organization responsible for the document. |
| Publication date | Date and available precision; unknown if unavailable. Track revisions separately. |
| Language | Original document language; identify multilingual material. |
| Jurisdiction/system | Relevant country or countries and named program/vehicle; distinct from publisher location. |
| Source type | Official record, announcement, company statement, technical publication, or secondary reporting. |
| Retrieval date | Date of access, separate from publication and event dates. |
| Copyright/license notes | Applicable terms, known reuse permissions, restrictions, and review notes. |
| Domain | Explicit subject-area label when known; do not infer it from language or publisher. |
| Document ID/version | Stable identifier and content hash or version reference when practical. |
| Parsing notes | Format, extraction issues, missing pages, OCR use, and locator limitations. |

Event dates and the temporal scope of claims should be captured when supported by the text. Retain original passages and source locations wherever storage is permitted. Dates and facts must not be silently filled from assumptions.

## Rights and access

Inclusion in a research corpus does **not** grant redistribution rights. Public accessibility is not equivalent to an open license, and the project's MIT license does not cover third-party materials.

Review applicable access and reuse terms before ingestion or publication. Do not bypass access restrictions. Where redistribution is not permitted or is unclear, keep source files out of the public repository and publish permitted metadata, links, and independently authored annotations instead. Review excerpts, translations, and derived artifacts separately.

All production corpora, indexes, and generated outputs must be stored outside every Git working tree. Ignore rules are secondary protection, not permission to store private data in Git. Adding any source material publicly requires explicit redistribution approval and rights review.

## Evidence handling

Preserve corrections, updates, and conflicting statements rather than silently replacing historical evidence. Record when a conclusion is valid only as of a particular date. Retain the difference between source assertions, demonstrated events, analyst calculations, and uncertain inferences.

Label translations and link them to original text. Review domain terminology and negation before using a translation to support a claim. Follow the evidence-status framework in the [aerospace taxonomy](../src/domains/aerospace/taxonomy.md) for that domain; other domains may require different vocabularies.

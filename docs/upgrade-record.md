# Verification upgrade record

Before: standard-library prepared-text ingestion, in-memory TF-IDF retrieval, metadata/paragraph references, Hit@5, private filesystem validation, legacy CLI. No web fetching or verdicts.

Baseline commit `70bf255`: 19 tests, two Windows symlink permission skips, no failures. Hit@5 6/6; two unanswerable questions excluded. Commands: `python -B -m unittest discover -s tests -v`; `python -B src/research_search.py --mode demo evaluate`.

Plan: preserve local code; reuse retrieval/privacy helpers; add small source/model/verification/CLI modules; make human review explicit; test dangerous failure modes; document limitations; inspect staged content; commit/push feature branch.

Upgrade regression: 38 tests with the same two skips; optional PDF physical-page test executed. `python -B src/verify.py verify --demo --output markdown` produced FALSE from a reviewed invented negative record. No real-world accuracy is claimed. Live search is unavailable; manual HTTPS fetching and HTML parsing were tested against NASA (214 extracted paragraphs). A live manual-URL review returned candidate evidence with no verdict; SEARCH_UNAVAILABLE remained explicit. No downloaded page was retained in Git.

Weaknesses: small registry; over/under-grouped dependencies; limited decomposition; human-dependent semantic judgments; UTF-8/paragraph-layout HTML; in-process PDF parser/no OCR; no alias or translation-quality validation. No production data is required by tests.

## Completion audit, 2026-09-28

Started from clean feature branch at `8a38db6`, where the vertical slice was already implemented and published. Re-ran baseline: 38 tests, two skips; Hit@5 6/6. Preserved retrieval code and source-policy architecture.

Fixed evidence-ID collisions for repeated atomic claims, stale review labels on reassessment, malformed review-object handling, and demo CLI review-only semantics. Added four regression tests. Evidence-ID migration requires regenerating private candidate reports and rebinding reviews; old IDs are explicitly rejected.

Final validation: 42 tests, two Windows symlink skips, optional PDF physical-page extraction executed; synthetic demo returned FALSE from an explicit invented negative record; both review-only CLI paths withheld the verdict. Manual NASA homepage HTTPS fetching and parsing succeeded with 213 extracted paragraphs; content stayed in memory. No current-web search provider was configured or claimed tested. No production captures, private paths or credentials were added to Git.

Commands: `python -B -m unittest discover -s tests -q`, `python -B src/research_search.py --mode demo evaluate`, `python -B src/verify.py verify --demo --output markdown`, and `git diff --check`. On this host Python was invoked using the bundled runtime because it is not on PATH.

## Automatic discovery upgrade, 2026-09-28

Started from merged main `dd3b64e` on `feature/automatic-web-search`. Baseline: 42 tests, 40 passed and two Windows symlink skips; verification demo FALSE from the synthetic negative record; private manual-capture workflow exercised by the existing suite. No retrieval or verdict requirements were replaced.

Added a documented Brave Web Search API adapter, structured results, bounded deterministic intents, exact-host qualification, unregistered-source diagnostics, conservative deduplication, publisher-diverse selection, query/error manifests, question-file input and no-bundle CLI research. Manual URL/offline modes remain supported. Search failures suppress automatic verdicts, and snippets remain outside evidence. API response diagnostics are sanitized and parser stderr is contained in production research.

No Brave API key was available in the documented environment variable. Live search was not performed and remains unverified; tests mock the provider and HTTP contract. No credentials, production captures or search responses are committed. Search snapshots and fetched documents are written only to validated external private directories. See the automatic-search guide for configuration and cost bounds.

Validation: 64 tests, 62 passed, the same two Windows symlink skips, zero failures. Retrieval Hit@5 remains 6/6. A synthetic discovery run issued five mock queries, selected and parsed two approved sources, retrieved two candidate passages, identified one dependency hint and withheld the verdict. Full-suite command: `python -B -m unittest discover -s tests -q`; retrieval command: `python -B src/research_search.py --mode demo evaluate`. The public demo remains functional; no live-search result is claimed.

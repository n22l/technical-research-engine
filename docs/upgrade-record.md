# Verification upgrade record

Before: standard-library prepared-text ingestion, in-memory TF-IDF retrieval, metadata/paragraph references, Hit@5, private filesystem validation, legacy CLI. No web fetching or verdicts.

Baseline commit `70bf255`: 19 tests, two Windows symlink permission skips, no failures. Hit@5 6/6; two unanswerable questions excluded. Commands: `python -B -m unittest discover -s tests -v`; `python -B src/research_search.py --mode demo evaluate`.

Plan: preserve local code; reuse retrieval/privacy helpers; add small source/model/verification/CLI modules; make human review explicit; test dangerous failure modes; document limitations; inspect staged content; commit/push feature branch.

Upgrade regression: 38 tests with the same two skips; optional PDF physical-page test executed. `python -B src/verify.py verify --demo --output markdown` produced FALSE from a reviewed invented negative record. No real-world accuracy is claimed. Live search is unavailable; manual HTTPS fetching and HTML parsing were tested against NASA (214 extracted paragraphs). A live manual-URL review returned candidate evidence with no verdict; SEARCH_UNAVAILABLE remained explicit. No downloaded page was retained in Git.

Weaknesses: small registry; over/under-grouped dependencies; limited decomposition; human-dependent semantic judgments; UTF-8/paragraph-layout HTML; in-process PDF parser/no OCR; no alias or translation-quality validation. No production data is required by tests.

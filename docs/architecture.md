# Architecture

The original `research_search.py` ingestion, TF-IDF ranking, privacy checks and evaluation are unchanged; `space_search.py` remains compatible.

The separate `verify.py` CLI composes `verification_models.py` (records), `web_sources.py` (policy/fetch/parse), `verification.py` (provider protocol, query intents, existing retrieval, dependency hints, citations, reviewed assessment and rendering), and optional `domains/aerospace/rules.py` maturity guards.

Request → atomic claims → bounded query intents → search provider/manual URLs → search results → source policy → source selection → safe fetch → parse → existing lexical retrieval → candidate evidence → separate human review → citation/temporal/scope checks → assessments → private report.

`search_discovery.py` owns the structured provider protocol, Brave adapter, deterministic query generation, conservative URL normalization, policy decisions, publisher-diverse selection and fixture evaluation. `domains/aerospace/search_hints.py` supplies optional query vocabulary. The API layer is implemented and mock-tested; live integration remains unverified. Search snippets cannot enter the document parser or evidence retrieval.

No LLM, database, frontend, credential discovery or deployment service exists. Only documented environment variables configure the provider. Capture reuse is explicit via offline bundles, not an automatic freshness-assuming cache. Grouping uses publisher, canonical identity, links and similarity; it may over-group and never proves remaining groups independent. No vote counting determines truth.

Fetching pins a validated public DNS address with TLS hostname validation and rejects redirects, credentials, compressed responses and oversized downloads. There is no proxy, authentication/paywall bypass or script execution. PDF parsing is in-process: byte/page limits are not a hardened parser sandbox. HTML supports UTF-8 and paragraph/list tags, not arbitrary dynamic layouts.

Local default: `local_search.py` supplies a bounded, robots-aware crawler over approved source-policy hosts and optional reviewed `crawl_seeds`. The private lexical index is reused for up to 24 hours and invalidated by policy changes. Selected URLs still pass through the existing safe fetch/parser and human-review pipeline; cached index text is never evidence. Brave remains explicitly selected, with no automatic paid fallback. SearXNG is deferred.

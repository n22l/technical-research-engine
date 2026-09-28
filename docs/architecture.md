# Architecture

The original `research_search.py` ingestion, TF-IDF ranking, privacy checks and evaluation are unchanged; `space_search.py` remains compatible.

The separate `verify.py` CLI composes `verification_models.py` (records), `web_sources.py` (policy/fetch/parse), `verification.py` (provider protocol, query intents, existing retrieval, dependency hints, citations, reviewed assessment and rendering), and optional `domains/aerospace/rules.py` maturity guards.

Request → atomic claims → planned search intents → manual URLs/local captures → policy → fetch/parse → existing lexical retrieval → candidate evidence → separate human review → citation/temporal/scope checks → assessments → private report.

No LLM, database, frontend, credential discovery or deployment service exists. Capture reuse is explicit via offline bundles, not an automatic freshness-assuming cache. Grouping uses publisher, canonical identity, links and similarity; it may over-group and never proves remaining groups independent. No vote counting determines truth.

Fetching pins a validated public DNS address with TLS hostname validation and rejects redirects, credentials, compressed responses and oversized downloads. There is no proxy, authentication/paywall bypass or script execution. PDF parsing is in-process: byte/page limits are not a hardened parser sandbox. HTML supports UTF-8 and paragraph/list tags, not arbitrary dynamic layouts.

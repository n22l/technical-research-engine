# Automatic web discovery

Discovery is implemented with the documented [Brave Web Search API](https://api-dashboard.search.brave.com/api-reference/web/search/get), using HTTPS GET `/res/v1/web/search`. Only fetched and parsed documents can become evidence. API titles, descriptions, summaries and snippets are never evidence.

## Configuration and first run

Python 3.10+ and Git are required; the search adapter uses the standard library. Set these environment variables in the process running the engine:

- `TECH_RESEARCH_DATA_DIR`: an existing private directory outside every Git checkout.
- `TECH_RESEARCH_SEARCH_PROVIDER=brave`: enables API discovery. Default is `manual`.
- `BRAVE_SEARCH_API_KEY`: your Brave subscription token. Supply it through your environment or secret manager; do not paste it into a committed file or shell history. The engine reads only this named variable, sends it in the authentication header, and never persists it.

No dotenv file is loaded, and no credentials are searched for. API calls transmit generated research queries to Brave; `--question-file` avoids shell history, not disclosure to the configured search provider. Use `--offline` for local-only research.

```powershell
$env:TECH_RESEARCH_SEARCH_PROVIDER = 'brave'
python -B src/verify.py research "Has China reflown a recovered orbital-class booster?" --domain aerospace --review-only
python -B src/verify.py research "Is the James Webb Space Telescope located at the Sun-Earth L2 region?" --search-provider brave --review-only --max-queries 5 --results-per-query 5 --max-candidate-urls 20 --max-sources 8
python -B src/verify.py research --question-file question.txt --search-provider brave --review-only
```

The question file must be UTF-8 inside the configured private directory. Production terminal output contains counts/status only; review passages and source-policy decisions are in external `result-*.json`. Review-only runs withhold verdicts. Automatic discovery does not satisfy the human-review requirements.

Manual URLs can be merged with automatic discovery using repeated `--url` arguments or an existing bundle. To avoid API calls explicitly use `--search-provider manual`. Offline mode never instantiates or calls the API provider, even when environment configuration enables it.

```powershell
python -B src/verify.py research --bundle request.json --search-provider manual --review-only --domain aerospace
python -B src/verify.py research "Webb orbit" --url https://www.nasa.gov/ --search-provider manual --review-only
python -B src/verify.py verify --bundle reviewed.json --offline --domain aerospace
python -B src/verify.py verify --demo --output markdown
```

## Bounds and costs

Defaults: eight maximum queries, five results per query, twenty candidate URLs, eight fetches. Hard ceilings are 40, 20, 100 and 20 respectively. Five deterministic intents are generated per atomic claim; the query budget is distributed round-robin across claims. Therefore a one-claim request normally issues five calls, not eight. Query text is bounded to the provider's 600-character/75-word constraints; long input can lose detail and requires reviewer inspection.

The adapter makes at most one call per second, with a 15-second socket timeout, a two-megabyte response limit, no pagination and no retries. Authentication, rate-limit and other provider failures stop further API calls. No payment, subscription or credit redemption is automated.

As checked on 2026-09-28, [Brave's pricing page](https://brave.com/search/api/) advertises $5 per 1,000 Search requests and $5 monthly credits. Account eligibility and pricing can change; check your plan before enabling calls. Five calls are approximately $0.025 before credits under that published rate. These charges are separate from Codex included usage.

## Query generation and selection

Each claim produces PRIMARY_SOURCE, OFFICIAL_RECORD, INDEPENDENT_CONFIRMATION, LATEST_UPDATE and CONTRADICTION_OR_CORRECTION intents. A recognized publisher in the claim can supply a policy host hint; otherwise queries remain generic. Optional aerospace hints live in the aerospace domain module. No LLM is used, and queries never constitute evidence.

URLs are normalized conservatively: HTTPS only, lowercased hosts, default port and fragments removed, known tracking parameters removed. Meaningful query parameters retain ordering, repetition and encoding. Original discovered URLs remain in private provenance. Manual URLs retain their exact capture identity so existing review/capture bundles still work.

The existing exact-host registry qualifies each candidate as APPROVED_EVIDENCE_SOURCE, DISCOVERY_ONLY, REJECTED or UNKNOWN. Unknown sources carry UNREGISTERED_SOURCE for policy review, even when a hostname ends in `.gov` or `.edu`. They are never fetched automatically. This milestone retains the small NASA/FAA/CNSA/SpaceX/Reuters registry; it does not claim broad coverage.

Approved candidates are ordered by tier, primary status and API rank, with one source per publisher selected before repeats. This is a discovery heuristic, not an evidentiary-strength score. Publication dates and dependencies are evaluated after fetching; snippets do not supply either. The bounded candidate pool can miss authoritative results appearing later. The report marks truncation. No second-hop crawling or paywall bypass is performed.

## Failures and audit

SEARCH_UNAVAILABLE means configuration is absent/unsupported. SEARCH_AUTH_FAILED, SEARCH_RATE_LIMITED and SEARCH_PROVIDER_ERROR identify failed API attempts. SEARCH_NO_RESULTS records a successfully completed search with no returned web results. A completed search without approved evidence can yield INSUFFICIENT_PUBLIC_EVIDENCE; a failed automatic search withholds the verdict and exposes the process failure. Manual URLs can still produce candidates during a search failure. The existing explicitly limited manual-only verification behavior is preserved.

The private manifest records query intents and actual attempts, per-query status/count/time, provider name, nonsecret bounds, bounded result metadata, original/normalized URLs, policy decisions, selected/rejected URLs, fetch/parse results, hashes, captures, evidence IDs and dependency hints. Failed attempts count toward the query limit; there are no hidden retries. Results beyond the candidate cap are counted but not retained individually.

Search results are snapshots in the private report, not an automatic reusable cache. A new online run queries current results. To replay without API cost, construct an offline bundle from the saved selected URLs and capture records and retain the original discovery manifest. Offline replay never treats saved snippets as evidence.

## Validation and limitations

The adapter contract, error mapping, bounds, URL validation, source selection, snippet isolation, private CLI, offline replay and temporal safeguards are covered by synthetic tests. `evaluate_discovery` accepts selected URLs, expected authoritative domains and forbidden domains, reporting domain recall and labeled URL precision at k. It measures fixture selection only, not production search quality or factual accuracy.

No Brave key was configured during implementation, so live API integration remains unverified. The NASA manual fetch from the previous milestone is not a live search test. Search quality, registry coverage, decomposition, dependency detection, multilingual retrieval and semantic entailment remain limited. Human review remains mandatory for factual assessments.

## Free local default

Question-only research now defaults to `local`, a free bounded crawler and private lexical index. No API key is required. Existing bundles and explicit manual URLs retain manual behavior unless a provider is selected. Brave remains an explicit optional fallback (`--search-provider brave`); there is no automatic paid fallback. SearXNG is not implemented.

```powershell
python -B src/verify.py research "Has China reflown a recovered booster?" --review-only
python -B src/verify.py research "booster reflight" --search-provider local --refresh-local-index --max-crawl-pages 12 --review-only
```

Set `TECH_RESEARCH_DATA_DIR` to an existing directory outside Git. Local discovery starts at approved registry hosts, or their optional `crawl_seeds` list, follows same-host links one level deep, and attempts at most 12 pages (configurable 1–30). Robots requests add at most one request per attempted host. Unavailable/denying robots.txt fails closed. Requests are paced, redirects remain rejected, and existing public-DNS/TLS/download protections apply. No search engine result pages are scraped.

Immutable `local-index-*.json` snapshots stay in the private directory. Compatible snapshots are reused for up to 24 hours; `--refresh-local-index` forces a new crawl. Changed source policy invalidates cache reuse. Results describe this bounded index, not whole-web coverage or guaranteed current facts. Query-independent shallow crawling can miss relevant pages; add reviewed topic-specific seeds for better coverage. Selected documents are fetched again through the evidence pipeline; index text and search snippets never support verdicts.

Local-provider tests cover robots denial/failure, depth/page bounds, cross-host exclusion, cache reuse/invalidation, and key-free configuration. Full suite: 68 tests, 66 passed, two Windows symlink skips. Live crawling is not yet validated. Automatic refresh does not delete old private snapshots.

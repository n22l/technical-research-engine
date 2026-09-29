# Automatic web discovery

Discovery defaults to a free local crawler/index (see below). Optional external discovery uses the documented [Brave Web Search API](https://api-dashboard.search.brave.com/api-reference/web/search/get), using HTTPS GET `/res/v1/web/search`. Only fetched and parsed documents can become evidence. API titles, descriptions, summaries and snippets are never evidence.

## Configuration and first run

Python 3.10+ and Git are required; the search adapter uses the standard library. Set these environment variables in the process running the engine:

- `TECH_RESEARCH_DATA_DIR`: an existing private directory outside every Git checkout.
- `TECH_RESEARCH_SEARCH_PROVIDER=brave`: enables API discovery. Question-only input defaults to `local`; existing bundles/manual URLs default to `manual`.
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

The existing exact-host registry qualifies each candidate as APPROVED_EVIDENCE_SOURCE, DISCOVERY_ONLY, REJECTED or UNKNOWN. Unknown sources carry UNREGISTERED_SOURCE for policy review, even when a hostname ends in `.gov` or `.edu`. They are never fetched automatically. The registry is explicit and remains limited; see the local-provider section for coverage.

Approved candidates are ordered by tier, primary status and API rank, with one source per publisher selected before repeats. This is a discovery heuristic, not an evidentiary-strength score. Publication dates and dependencies are evaluated after fetching; snippets do not supply either. The bounded candidate pool can miss authoritative results appearing later. The report marks truncation. Provider API results do not trigger unrestricted crawling or paywall bypass.

## Failures and audit

SEARCH_UNAVAILABLE means configuration is absent/unsupported. SEARCH_AUTH_FAILED, SEARCH_RATE_LIMITED and SEARCH_PROVIDER_ERROR identify failed API attempts. SEARCH_NO_RESULTS records a successfully completed search with no returned web results. A completed search without approved evidence can yield INSUFFICIENT_PUBLIC_EVIDENCE; a failed automatic search withholds the verdict and exposes the process failure. Manual URLs can still produce candidates during a search failure. The existing explicitly limited manual-only verification behavior is preserved.

The private manifest records query intents and actual attempts, per-query status/count/time, provider name, nonsecret bounds, bounded result metadata, original/normalized URLs, policy decisions, selected/rejected URLs, fetch/parse results, hashes, captures, evidence IDs and dependency hints. Failed attempts count toward the query limit; there are no hidden retries. Results beyond the candidate cap are counted but not retained individually.

Search results are snapshots in the private report, not an automatic reusable cache. A new online run queries current results. To replay without API cost, construct an offline bundle from the saved selected URLs and capture records and retain the original discovery manifest. Offline replay never treats saved snippets as evidence.

## Validation and limitations

The adapter contract, error mapping, bounds, URL validation, source selection, snippet isolation, private CLI, offline replay and temporal safeguards are covered by synthetic tests. `evaluate_discovery` accepts selected URLs, expected authoritative domains and forbidden domains, reporting domain recall and labeled URL precision at k. It measures fixture selection only, not production search quality or factual accuracy.

No Brave key was configured during implementation, so live API integration remains unverified. The NASA manual fetch from the previous milestone is not a live search test. Search quality, registry coverage, decomposition, dependency detection, multilingual retrieval and semantic entailment remain limited. Human review remains mandatory for factual assessments.

## Free local default

Local discovery uses a persistent private index capped at 500 documents, with
at most 500 attempted pages/resources per refresh, 100 attempts per host, two
link levels, and a 120-second scheduling budget. An in-flight network call and
its pacing delay can finish after that budget. These are limits, not promised
coverage. `--max-crawl-pages` accepts 1–500 and defaults to 500.

Refresh saves unfinished URLs and preserves existing entries. The next explicit
`--refresh-local-index` (or UI refresh checkbox) continues pending discovery.
Ordinary searches reuse the snapshot for up to 24 hours. Older documents can
remain after failed refreshes; the UI reports stale-document and pending-URL
counts. Discovery metadata is never evidence: selected documents are fetched
again and require hash-bound human review before verification.

The exact-host registry includes NASA, FAA, CNSA, SpaceX, Reuters, ESA and JAXA.
NASA missions, ESA Space Transportation and JAXA rockets are topic starting
pages. Local configuration can add `crawl_seeds`, `sitemaps`, and `feeds` URL
lists to source-policy rules. Robots-advertised sitemaps are discovered
automatically. Sitemap indexes, URL sets, RSS and Atom are supported, limited
to approved same-host URLs, five discovery feeds per host per refresh, and a
3,000-URL saved frontier. XML DTDs/entities and non-UTF-8 XML are rejected.

Robots restrictions, crawl delays, pinned public HTTPS fetching, no redirects,
byte limits and source-policy checks remain enforced. Discovery XML is limited
to two megabytes. Index snapshots use validated external private storage only;
old schema snapshots are ignored rather than altered.

Ranking weights rare query terms, title matches, phrase matches and query-term
coverage. Repetition has a capped contribution. Obvious HTML navigation,
headers, footers and scripts are removed from the discovery text only; original
evidence/captures and citation offsets remain untouched. This is lexical
ranking, not semantic proof or a guarantee of relevance.

The expanded-index suite includes deterministic sitemap/feed, resume, robots,
time-budget, failed-refresh retention, bounds and ranking checks. Live coverage
is constrained by each publisher's robots policy and network availability.

## Optional SearXNG secondary provider

The adapter uses SearXNG's documented [JSON Search API](https://docs.searxng.org/dev/search_api.html), sending GET requests to `/search` with `q`, `format=json`, `categories=general`, and `pageno=1`. Configure an instance you operate or are authorized to use; the engine does not select public instances or install a server automatically. JSON output must be enabled in the instance's `search.formats`; many public instances disable it and return HTTP 403.

```powershell
$env:TECH_RESEARCH_SEARXNG_URL = 'https://your-search-host.example'
python -B src/verify.py research "booster reflight" --search-provider searxng --review-only
```

Replace the example with your real HTTPS instance base URL. Optional URL path prefixes are supported. This version requires public HTTPS on port 443 with standard TLS validation: loopback/private-network endpoints, embedded credentials, query/fragment configuration, and redirects are rejected. It does not weaken the document fetcher's SSRF protections to support local HTTP instances. An explicitly configured instance has transport permission only; it never becomes an approved evidence publisher.

No search API key or automatic paid fallback is used. SearXNG hosting and its upstream engines may have costs or restrictions. Generated queries are shared with the configured instance and its upstream engines; no guarantees of availability, privacy, or search coverage are implied by the adapter.

Each query makes at most one request, paced at one per second with a 15-second socket timeout and two-megabyte response cap. Only the first requested number of results is retained; no pagination or retries occur. Authentication/JSON-disabled (401/403), rate-limit (429), malformed response, unavailable engines, and other errors are explicit process failures. Even partial upstream-engine outages suppress a factual verdict. Missing configuration returns SEARCH_UNAVAILABLE. Results are still filtered by the existing evidence policy; snippets never become evidence.

The endpoint and aggregate upstream failure count are recorded under `search.provider_details`. Tests cover API shape, failure mapping, DNS/redirect/download controls and end-to-end snippet isolation. No instance was configured during development, so live SearXNG integration remains unverified. Local search remains the default and Brave is still an explicitly selected fallback.

Expanded-index live check: a three-attempt NASA missions crawl indexed three documents, returned results, and preserved 139 pending URLs. This checks crawl/index integration, not factual accuracy or broad coverage.

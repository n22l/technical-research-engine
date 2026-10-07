# Technical Research Engine

> An evidence-grounded AI research and verification system for complex technical subjects.

Given a factual question or claim, the system is being developed to search authoritative public sources, retrieve supporting and contradicting evidence, compare source differences, and produce a concise answer or verification judgment with traceable citations.

**Current stage: local retrieval, automatic source discovery, and human-reviewed verification.** The default free local crawler/index has passed a bounded live NASA integration. Brave remains an optional adapter; its live API integration is unverified without credentials. No LLM is required. Retrieved text cannot instruct the engine or generate its own review labels.

## Implemented now

- Recursive bounded publisher discovery, explicit subdomains, coverage inventories,
  passage/sentence BM25 ranking and exact highlighted sentence context. See
  [retrieval usage, limits and benchmark](docs/retrieval-ranking.md).

Synthetic example: query `reusable booster reflight` returns a fictional Agency
article at `https://agency.example/flight`, title *Flight record*, with most relevant
sentence "The reusable booster completed reflight." and its containing paragraph.
Location: section *Flight*, extracted paragraph 1. Matched terms: reusable, booster,
reflight. This explains retrieval relevance, not factual truth.

- Preserved prepared-text ingestion, English/Chinese lexical passage retrieval, source metadata and Hit@5 evaluation, including the legacy CLI.
- Request/claim records; conservative semicolon/newline splitting or explicit atomic claims.
- Bounded deterministic query intents, Brave API adapter, URL deduplication and auditable source selection with publisher diversity.
- Configurable exact-host source policy; subdomains require explicit opt-in.
- Bounded public HTTPS fetching from manual URLs; inert UTF-8 HTML and optional physical-page PDF extraction.
- Original passages, hashes, source metadata, section/extracted-paragraph/character-span locators.
- Dependency hints, future-publication exclusion and explicitly reviewed supersession.
- Human-reviewed stance/scope/attribution assessments, conservative verdicts, insufficiency and unresolved conflicts.
- Citation integrity validation, review-only mode, JSON/Markdown and private run manifests/captures.
- Stable evidence IDs distinguish repeated atomic claims; reassessment clears stale review labels without modifying candidates.
- Aerospace guard against treating plans, landing or recovery as routine reuse.

## In development

Semantic verification depends on human annotations. Source qualification, dependency detection, decomposition and extraction need broader validation. Current tests are invented fixtures; no real-world verdict accuracy is claimed.

## Planned

Live search integration validation, evaluated semantic interpretation, substantive answer synthesis, held-out verification benchmarks, evidence-backed entity aliases, translation evaluation, cross-language retrieval and OCR. Cloud deployment is not required. A local browser interface is available.

## Local Web UI

Start the private browser workflow with `python -B launch.py --data-dir C:\ResearchPrivate`, then open
http://127.0.0.1:8000. Set `TECH_RESEARCH_DATA_DIR` to an existing external,
non-Git directory first. The UI supports research, source inspection, human
review, verification, private history, and JSON/Markdown export. Local search
is the default; Brave and SearXNG require explicit selection.
Enter a question → Research → Review evidence → Verify → Read/export.
Automatic source discovery does not eliminate human evidence review.
See [local UI setup and workflow](docs/local-ui.md).

The launcher checks private-folder writes and detects an existing server before
starting. Use an absolute path to `launch.py` when launching from another folder.
An older server must be stopped and restarted to load updated code.
See [acceptance improvements and frozen evaluation](docs/acceptance-improvements.md)
for retrieval coverage diagnostics, atomic claims and reviewed corrections.

## Run

Python 3.10+ and Git are required. Core workflows use the standard library. PDF support optionally requires `pypdf`; nothing is automatically installed.

```powershell
python -B src/research_search.py --mode demo search --question "refurbishment replacement parts"
python -B src/research_search.py --mode demo evaluate
python -B src/verify.py verify --demo --output markdown
python -B -m unittest discover -s tests -v
```

The verification demo and its `.example` URL are fictional. It demonstrates a reviewed negative record producing FALSE, not a judgment about real rockets.

For real research set `TECH_RESEARCH_DATA_DIR` to an existing external non-Git directory and create a private bundle following the [methodology](docs/verification-methodology.md):

```powershell
python -B src/verify.py research --bundle request.json --review-only --domain aerospace
python -B src/verify.py verify --bundle reviewed.json --offline --as-of 2026-06-01 --domain aerospace --output markdown
```

Production reports, including Markdown, stay inside private `result-*.json`; no passages are printed. The existing `space_search.py` and `SPACE_DATA_DIR` fallback remain supported. See [local retrieval](docs/local-retrieval.md).

## Verification philosophy

Evidence over plausibility. Primary sources first. Attribution is not independent confirmation. Repeated reporting is not multiple confirmations. Plans are not demonstrated capability. Uncertainty is valid. Source disagreements remain explicit.

A reviewer binds assessments to claims and document hashes and checks relevance, directness, scope and attribution. This is a human trust boundary, not an automatic entailment guarantee. Official/company statements establish announcements, not automatically the underlying event.

## Search and evaluation status

Question-only discovery defaults to the free local authoritative-site index. For optional Brave discovery, set `TECH_RESEARCH_SEARCH_PROVIDER=brave` and supply `BRAVE_SEARCH_API_KEY` through the process environment. No credentials are discovered or stored. Existing manual/offline workflows require no API key. Missing configuration reports SEARCH_UNAVAILABLE; API errors withhold automatic verdicts. Brave live API integration remains unverified because no key was available; local crawling has a bounded live integration check.

```powershell
python -B src/verify.py research "Has China reflown a recovered orbital-class booster?" --search-provider brave --domain aerospace --review-only
python -B src/verify.py research --question-file question.txt --search-provider brave --review-only
```

Use an existing external `TECH_RESEARCH_DATA_DIR`. Queries are sent to the configured provider; captures, discovery metadata and review reports stay outside Git. Default bounds are eight queries, five results per query, twenty candidates and eight fetches. Search snippets never become evidence, and unregistered sources require policy review. See [automatic web search](docs/automatic-web-search.md) for setup, costs, failure states and replay.

Baseline: 19 tests, two Windows symlink skips; synthetic Hit@5 6/6, with two unanswerable cases excluded. The upgrade adds synthetic verification/security regressions. Green tests do not establish real-world verdict accuracy. See [evaluation](docs/evaluation-plan.md).

Completion audit: 42 tests, including optional PDF page extraction, pass with two Windows symlink skips. Manual NASA HTTPS fetch/HTML extraction was exercised; live search remains unavailable. Both `research --demo` and `verify --demo --review-only` withhold the verdict.

Automatic-discovery upgrade: 64 tests, 62 passed and the same two skips; Hit@5 remains 6/6. Mocked end-to-end discovery selected/fetched two synthetic authoritative sources and withheld the verdict for review. No live API results or production search scores are claimed.

## Documentation

[Architecture](docs/architecture.md), [methodology](docs/verification-methodology.md), [source policy](docs/source-policy.md), [citation model](docs/citation-model.md), [multilingual research](docs/multilingual-research.md), [roadmap](docs/roadmap.md), [upgrade record](docs/upgrade-record.md), [public/private boundary](docs/public-private-boundary.md).

The first application is Aerospace Intelligence for US–China Space Watch / 中美航天观察. Editorial material stays private. This is an independent personal project, not an official university project. Original code, documentation and synthetic fixtures use the [MIT License](LICENSE); third-party sources retain their rights.

## Free local discovery default

Question-only research defaults to a bounded approved-site crawler/index with no API key. Use an external `TECH_RESEARCH_DATA_DIR`, then run `python -B src/verify.py research "booster reflight" --review-only`. The private index is reused for up to 24 hours; use `--refresh-local-index` to refresh. The incremental index holds up to 500 documents, discovers approved sitemap/feed URLs, and saves pending work between bounded refreshes. Coverage remains limited to approved hosts, not the entire web. Brave remains explicitly selectable as an optional fallback; paid fallback is never automatic. Existing manual/offline modes remain supported. See [configuration and limits](docs/automatic-web-search.md#free-local-default). Current tests: 94 passed, two skipped. A live NASA run indexed and refetched two pages, produced five evidence candidates, reused its private cache, and withheld the verdict for review. Optional SearXNG is available as an explicitly configured secondary JSON API provider; live integration is unverified.

The [approved source catalog](docs/source-catalog.md) lists the expanded government, research-organization and official company coverage, including refresh instructions.

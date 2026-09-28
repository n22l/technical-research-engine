# Technical Research Engine

> An evidence-grounded AI research and verification system for complex technical subjects.

Given a factual question or claim, the system is being developed to search authoritative public sources, retrieve supporting and contradicting evidence, compare source differences, and produce a concise answer or verification judgment with traceable citations.

**Current stage: local retrieval plus a human-reviewed verification vertical slice.** This is not an autonomous fact-checker. No LLM or search API is configured. Retrieved text cannot instruct the engine or generate its own review labels.

## Implemented now

- Preserved prepared-text ingestion, English/Chinese lexical passage retrieval, source metadata and Hit@5 evaluation, including the legacy CLI.
- Request/claim records; conservative semicolon/newline splitting or explicit atomic claims.
- Configurable exact-host source policy; subdomains require explicit opt-in.
- Bounded public HTTPS fetching from manual URLs; inert UTF-8 HTML and optional physical-page PDF extraction.
- Original passages, hashes, source metadata, section/extracted-paragraph/character-span locators.
- Dependency hints, future-publication exclusion and explicitly reviewed supersession.
- Human-reviewed stance/scope/attribution assessments, conservative verdicts, insufficiency and unresolved conflicts.
- Citation integrity validation, review-only mode, JSON/Markdown and private run manifests/captures.
- Aerospace guard against treating plans, landing or recovery as routine reuse.

## In development

Semantic verification depends on human annotations. Source qualification, dependency detection, decomposition and extraction need broader validation. Current tests are invented fixtures; no real-world verdict accuracy is claimed.

## Planned

Search API adapters, evaluated semantic interpretation, substantive answer synthesis, held-out verification benchmarks, evidence-backed entity aliases, translation evaluation, cross-language retrieval and OCR. No frontend or cloud deployment is required.

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

Manual URLs are the only implemented search provider. Online runs report `CURRENT_WEB_RESEARCH_UNAVAILABLE` and `SEARCH_UNAVAILABLE` even when supplied pages fetch. Search intents are planned, not falsely recorded as issued. No search credentials are read. Live search is unverified.

Baseline: 19 tests, two Windows symlink skips; synthetic Hit@5 6/6, with two unanswerable cases excluded. The upgrade adds synthetic verification/security regressions. Green tests do not establish real-world verdict accuracy. See [evaluation](docs/evaluation-plan.md).

## Documentation

[Architecture](docs/architecture.md), [methodology](docs/verification-methodology.md), [source policy](docs/source-policy.md), [citation model](docs/citation-model.md), [multilingual research](docs/multilingual-research.md), [roadmap](docs/roadmap.md), [upgrade record](docs/upgrade-record.md), [public/private boundary](docs/public-private-boundary.md).

The first application is Aerospace Intelligence for US–China Space Watch / 中美航天观察. Editorial material stays private. This is an independent personal project, not an official university project. Original code, documentation and synthetic fixtures use the [MIT License](LICENSE); third-party sources retain their rights.

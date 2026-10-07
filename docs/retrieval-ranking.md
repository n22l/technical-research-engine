# Site discovery and passage retrieval

This upgrade changes retrieval and presentation, not verdict rules. A retrieval
score is never truth confidence. Human review and validated citations remain required.

## Coverage

Publisher rules can list exact `crawl_hosts`, `crawl_seeds`, `sitemaps`, `feeds`,
`allowed_path_prefixes` and `excluded_path_prefixes`. Explicit host rules override
inherited publisher entries. No wildcard is added implicitly. The checked NASA
configuration adds only `science.nasa.gov`, verified against NASA Science originals.
Each host has its own robots check; unsafe/unavailable robots remains fail-closed
except the existing 404/410 handling. Redirect/public-address/HTTPS protections stay.

Robots-advertised and configured maps are prioritized over HTML page crawling.
Pages are interleaved after batches of maps to avoid starving indexing during a
short refresh; remaining sitemap work is retained rather than discarded.
Nested maps have separate depth (8), files-per-host-per-refresh (100), and discovered
URL/frontier (20,000) limits. The old five-map ceiling is removed. A sitemap article
starts at discovery depth zero regardless of URL path depth. RSS/Atom and HTML links
supplement maps. HTML link depth remains two; traps such as login, calendar, search,
pagination, sort, filter and session URLs are rejected. Meaningful document query
parameters remain; tracking parameters/fragments are normalized away.

Normal runs retain the existing 500-page index cap, 100 page attempts per host,
120-second scheduling budget and bounded request sizes/timeouts. Private inventory
records URL states, map progress and the remaining frontier. Coverage reports include
publisher, hosts/seeds, discovered/indexed/pending/failed/blocked URLs, map counts,
attempts and timestamps. Unexplored or limited discovery cannot report completion.
`COMPLETE_WITHIN_DISCOVERED_SCOPE` does not mean every publisher page is indexed.
Robots, JavaScript navigation, failed fetches, scope and budgets still limit coverage.

```powershell
python -B src/verify.py research "Webb Sun Earth L2" --site NASA --search-provider local
python -B src/site_index.py refresh --site NASA
python -B src/site_index.py refresh --site NASA --deep
python -B src/site_index.py coverage
python -B src/site_index.py reindex
```

Set `TECH_RESEARCH_DATA_DIR` to an existing external non-Git directory first.
The UI's Search publisher option selects all explicitly approved hosts of a publisher;
its refresh checkbox limits the new crawl to that publisher. Other publishers' stored
frontiers remain. Deep mode is explicit: ten minutes, 500 sitemap files per host and
50,000 discovered URLs, still at most 500 indexed documents. Network requests can
finish after the scheduling deadline. No paid provider is selected automatically.

## Storage and migration

Schema 4 stores page metadata plus original paragraphs/locations and hash-named
private raw captures. ETag and Last-Modified enable conditional requests; 304 reuses
the parsed representation. Reindex verifies capture hashes and rebuilds passages
without network calls. Sentence structures are computed deterministically at query
time to avoid duplicate persisted text. JSON snapshots and captures never enter Git.

Schemas 2/3 remain readable. Legacy entries lacking captures require refetch (reindex
reports their count). Policy changes requalify retained URLs rather than deleting
old snapshots. Schema/policy refresh writes a new snapshot. Old immutable research
records remain; changed parsing/ranking can require research and review again rather
than applying old reviews to changed evidence. Document parsing for the index is
bounded at 200,000 characters/2,000 paragraphs; oversized documents report failure.

## Ranking and exact evidence

Passage BM25 uses body term frequency, inverse corpus frequency and length
normalization. Coverage, exact quoted/Chinese phrases, all-terms-in-one-sentence,
and the smallest token window boost matches. Title/heading matches contribute only
a modest boost after body relevance qualifies. Explicit subject/country constraints
remain. Hyphenated model names and numbers survive alongside lexical tokens; the
small configured aliases include reflight/re-flight. No automatic translation or
unverified technical identity aliases are introduced.

Page order aggregates its strongest passage and downweights recognizable homepages.
The local result keeps external `snippet` empty and puts fetched evidence in
`local_match`. Verification refetches/parses and independently validates candidates;
it never accepts a discovery snippet as evidence. Up to two distinct paragraphs per
document enter candidate review; duplicate paragraphs are suppressed. Existing
source-selection diversity and dependency diagnostics remain separate from scores.

Sentence segmentation supports English/Chinese punctuation and common abbreviations
and decimals. Every best sentence is an exact slice of its containing paragraph;
paragraph offsets still refer to extracted document text, not HTML byte offsets.
IDs, source hash, title/URL/publisher, section, extracted paragraph and physical PDF
page remain available. Sentence offsets are relative to the paragraph. UI highlights
use validated character spans and text nodes, never HTML injection or modified source
wording. The whole paragraph remains the evidence unit, with an expandable match
explanation. JSON and Markdown include the best sentence and paragraph context.

Diagnostics distinguish matching content, missing corpus coverage and weak relevance;
an empty result does not establish absence of a fact. Limitations include lexical
aliases, implicit references, extraction quality, unknown dates and incomplete site
coverage. Recency does not override historical relevance. Near-duplicate dependency
analysis remains heuristic. Optional within-document search and semantic reranking
are future work.

## Reproducible evaluation

Baseline main: `dd8202782ab899ab14736893412360f7d5379c18`. Before editing, 127
tests ran: 125 passed, two optional tests skipped. Legacy demo Hit@5 was 6/6.

```powershell
python -B src/evaluate_passages.py --baseline-ref dd8202782ab899ab14736893412360f7d5379c18
python -B -m unittest discover -s tests -q
```

The seven deliberately adversarial synthetic cases include six title-only distractors
per expected paragraph. They exercise combinations, phrases, technical tokens,
aliases, Chinese, mixed language and a synthetic PDF locator. This is a development
regression fixture, not a representative accuracy estimate or held-out benchmark.

| Metric | Baseline | Passage ranking |
| --- | ---: | ---: |
| Document Hit@5 | 0/7 | 7/7 |
| Passage Hit@5 | 6/7 | 7/7 |
| Passage MRR | 0.857 | 1.000 |
| Best sentence Hit@1 | unavailable | 7/7 |

The zero document baseline specifically exposes title-only domination in these
constructed cases; it does not describe general engine performance. Without
`--baseline-ref`, the script reports an explicitly labeled current lexical ablation.
A 10,000-short-paragraph local timing measured about 2.9 seconds after caching token
expansions (previous prototype 10.4 seconds); timings vary with document length.

Final suite: 138 tests run, 136 passed and two optional tests skipped. JavaScript
syntax and whitespace checks passed. A disposable browser run confirmed publisher
selection, best-sentence highlighting, full paragraph context and match explanations.

## Live smoke checks, 2026-10-07

`tests/live_passage_smoke.py` performs three explicit robots-checked NASA fetches.
All three returned candidates. Full exact sentences and locators are saved only in
the external private report. These test several requested categories, not a complete
site crawl or a factual verdict:

- Quoted phrase/subdomain: `"halo orbit"`, [NASA orbit illustration](https://science.nasa.gov/asset/webb/webbs-orbit-at-sun-earth-lagrange-point-2-l2/).
- Three-plus terms/deep article: `Webb Sun Earth L2`, [NASA journey article](https://science.nasa.gov/blogs/webb/2022/01/21/webbs-journey-to-l2-is-nearly-complete/).
- PDF: `primary mirror size`, [NASA Webb fact sheet](https://science.nasa.gov/wp-content/uploads/2024/08/webbfactsheet.pdf).

Publication passages, captures, inventories and research reports are excluded from
the public change. The browser smoke uses entirely fictional evidence.

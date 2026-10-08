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
The recovery scheduler now attempts an available page after two map attempts,
including failed maps. Failed fetches persist a bounded retry backoff (five minutes
up to one day); refresh does not bypass that backoff. Gzip sitemap files are accepted
only within both compressed and decompressed two-megabyte limits, with the same
DTD/entity rejection as ordinary XML.
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

Recovery changes: legacy page-text records are excluded from discovery results until
their actual paragraphs are indexed. A fresh snapshot timestamp no longer hides
eligible unfinished migration. Legacy URLs reserve queue slots and receive page
priority; the UI reports legacy and passage-indexed counts separately. Failed URLs
remain subject to retry backoff. Completion still depends on publisher accessibility.

The recovery regressions reproduce sitemap failure starvation, gzip expansion limits,
incomplete migration inside a fresh schema-4 snapshot, and article-vs-homepage
selection before duplicate suppression. The follow-up below adds verified source
entry points and explicit entity constraints; broader discovery remains bounded.

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

## Retrieval recovery follow-up, 2026-10-08

The default seeds now include two fetched/parsed NASA rocket references and an
accessible CAS article about Kinetica-2. These are entry points on already-approved
hosts, not new publisher approvals. Explicit seeds remain admissible when another
publisher has filled the discovered-URL inventory, and outrank ordinary frontier
pages after legacy migration priority. Blocked legacy pages back off for one hour,
so each new question does not immediately repeat failed robots checks. They remain
pending for later policy-compliant retries. Legacy refetches omit conditional
validators so a 304 cannot indefinitely preserve a text-only record.

Fetch/parse failures retain bounded reason codes. Publisher coverage distinguishes
an HTTP failure, a network/fetch failure, and HTML with scripts but no extractable
paragraphs. SpaceX vehicle URLs returned such shells in the live check; CNSA's
connection failed. Neither is evidence that those publishers lack information.
No JavaScript execution, access-control bypass, unapproved host or paid fallback
was added. HTML parsing now honors explicitly declared UTF-8, GB2312/GBK/GB18030,
Big5 and Windows-1252 encodings with strict decoding, retaining exact extracted
paragraph locations rather than replacement characters.

Company/vehicle aliases and numbered Crew/CRS/Artemis identities constrain retrieval.
Mixed English/Chinese boundaries work without spaces. A title or section heading
may supply identity context, but not capability words, and a conflicting body
identity cannot be rescued by the title. This is lexical filtering, not entity
resolution or entailment. Unknown names, implicit pronouns and complex comparisons
remain limitations. Publisher-filtered diagnostics use the actual indexed passages,
not unrelated publishers or legacy page text.

`data/evaluation/source-cases-v1.json` freezes eight development questions: paired
English/Chinese NASA and CAS queries plus wrong-company/missing-mission controls.
Expected passages were inspected against source text and bound by paragraph hashes;
the fixture has its own normalized-line-ending checksum. Human sign-off is still
pending. A changed paragraph fails the frozen check instead of silently relabeling it.

```powershell
python -B src/evaluate_sources.py --data-dir C:\ExternalEvaluationFolder --refresh
python -B src/evaluate_sources.py --data-dir C:\ExternalEvaluationFolder
```

Use a separate existing non-Git folder. The first command explicitly fetches a
bounded, robots-checked set of known-source seeds. The second replays the private
snapshot without network calls. Captures and full source text stay outside Git.
Cold acquisition and offline replay passed 8/8 on this small development set; this
is not a held-out accuracy estimate or evidence of general sitewide recall.
The SpaceX “both stages” case expects related context, not a positive verdict;
the China engine cases identify future plans, not demonstrated reflight.

Cold and legacy-index regressions also exercise discovery through citation-validated
human review in both languages, reject another company's page, and require that no
unreviewed verdict is emitted. Real targeted private-index refreshes increased
passage-indexed documents from 4 to 21, leaving 25 legacy pages. SpaceX and China
engine queries returned candidates in English and Chinese; a nonexistent numbered
mission returned none. Larger publisher coverage and unavailable sources remain
incomplete; these results must not be described as full research readiness.

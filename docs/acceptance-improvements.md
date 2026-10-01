# Acceptance improvements

## Verification and review

Completed flight, landing and reuse claims require DEMONSTRATED or OPERATIONAL
status plus the corresponding milestone. A reusable vehicle's first flight does
not establish reflight; landing does not establish reuse. A plan word elsewhere
in a completed-performance claim cannot bypass this guard. These are conservative
rules, not autonomous semantic verification.

Simple English conjunctions with repeated auxiliaries are split automatically.
For more complex English or Chinese requests, enter one atomic claim per line in
Research options. Explicit claims take precedence and retain the original request.
Reviewed findings are assembled only from eligible evidence and reviewer-written
facts. Results compare supporting, contradicting and qualifying sources per claim.

Under Temporal, translation & maturity details, reviewers can select earlier
evidence corrected by a passage and explain why. Corrections require a newer dated
non-company source, direct observation and matching scope. The engine still checks
eligibility, review acceptance and claim identity before assigning OUTDATED.

## Frozen retrieval check

Run `python -B src/evaluate_frozen.py`. Version 1 is stored in
`data/evaluation/retrieval-v1.json` with a SHA-256 integrity file. It contains ten
English/Chinese cases, two short public-source excerpts with original URLs and
locators, and two explicitly synthetic distractors. Codex inspected the public
originals and expected matches; independent human validation remains outstanding.
Do not describe these labels as independently human-approved.

The current ranker passes 10/10 cases, versus 7/10 with subject filtering disabled.
This is an ablation on a small development fixture, not a historical baseline,
held-out evaluation, or real-world factual accuracy measurement. Positive cases
require an expected passage in the first five results; negative cases require no
results. Broader precision and recall are not established by this test.

English/Chinese concept aliases enforce explicit country and selected subject
coverage. URL heuristics downweight homepages and listing pages. These heuristics
are limited, can reject valid implicit references, and do not resolve every entity.
Missing coverage means required concepts are absent from the available corpus;
weak relevance means concepts exist but no passage passes the matching rules.
Neither means the event did not occur or no public source exists. Approved hosts
can still have no indexed articles. Refresh/discover appropriate articles rather
than interpreting an empty result as a negative verdict.

The small corpus is versioned and intentionally includes missing-coverage cases.
Changes to questions, excerpts or expected labels require a new version and review,
not merely replacing the fingerprint to make a failing check pass.

## Reliable local startup

From the repository: `python -B launch.py --data-dir C:\ResearchPrivate`.
The private folder must already exist outside Git. Alternatively set
`TECH_RESEARCH_DATA_DIR`; `--data-dir` overrides it. `--port` selects another port.
The legacy `src/ui.py` entry point uses the same startup checks.

Startup creates, flushes and removes a small private write probe. A compatible
server using the same folder is reused. An occupied port, older server or different
folder produces an actionable message without killing any process. Stop an old
server with Ctrl+C and relaunch to load code updates. Storage failures identify
permissions/free-space checks without exposing private paths in HTTP responses.

Validation: 127 unit/integration tests run, 125 passed and two optional tests
skipped; JavaScript syntax checked. Tests include maturity contradictions, bilingual
retrieval, cache migration, startup preflight/reuse, storage errors and reviewed
temporal correction. A disposable browser fixture exercises research, explicit
claims, review and answer rendering; it does not validate production source coverage.

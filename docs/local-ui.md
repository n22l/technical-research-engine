# Local browser workflow

The UI uses Python's standard-library HTTP server and plain HTML/CSS/JavaScript.
It reuses the existing research, parsing, evidence candidate, assessment, and
Markdown export functions. No frontend build or additional dependency is needed.

## Start

From the repository root, with Python 3.10+:

```powershell
New-Item -ItemType Directory -Force C:\ResearchPrivate
$env:TECH_RESEARCH_DATA_DIR = 'C:\ResearchPrivate'
python -B src/ui.py
```

Open http://127.0.0.1:8000. An existing directory outside every Git repository is
required. Without valid configuration, a setup page explains what to do.
`--port 8001` selects another loopback port. Stop with Ctrl+C.

## Workflow

1. Enter a question or claim and select Research. Options include domain, date,
   language, explicit provider, manual URLs, and confirmed local-index refresh.
2. Inspect query/source counts, claims, parsed source cards, and evidence passages.
3. For every candidate, select relevance and save a human review. Relevant reviews
   require reviewer and rationale; assign stance, strength, basis and scope.
   Aerospace status and milestone, temporal basis and translation are under details.
4. Use Save, Save & next, Skip for now, and filters to work through candidates.
   Skipping does not count as review. Verify requires every candidate reviewed and
   at least one relevant passage; existing engine eligibility rules still apply.
5. Verify to see the engine assessment, citations, uncertainties, dependencies and
   source differences. Export JSON or Markdown explicitly when wanted.
6. Reopen saved UI runs from History. Sources lists the trusted policy. Settings
   reports provider availability without exposing credentials.

Reviews bind to server-selected evidence IDs, claims and capture hashes. Browser
input cannot replace those bindings. Changed captures invalidate prior results.
Concurrent stale tabs cannot overwrite newer reviews. One research worker runs at
a time. Existing CLI commands and verification rules remain unchanged.

## Privacy and security

Research captures, index/cache, reviews and immutable UI snapshots remain in the
external private directory. UI history includes UI runs only. Exports downloaded
explicitly through the browser go to its download destination; keep them private.
No research material belongs in Git. The UI never serves capture files or accepts
browser-selected filesystem paths. It serves only three named static assets.

The listener binds only 127.0.0.1. Exact Host and POST Origin checks, a per-process
API token, cross-site rejection and a restrictive CSP protect local requests.
Untrusted text is inserted with textContent. Links require HTTPS without embedded
credentials. Access logs omit research content; errors do not expose tracebacks or
secrets. The UI reports only whether optional providers are configured. Local is
always the UI default and paid fallback never happens automatically.

This is a single-user local application, not a hardened public server. Other
programs running as the same OS user remain within the trust boundary.

## Validation and limitations

Baseline: 78 tests, 76 passed and 2 skipped. With the UI: 90 tests, 88 passed and
2 skipped. New tests cover request handling, default local research, immutable
history, review/hash binding, stale reviews, changed captures, exports, failed
search, secret omission, token/origin/host checks and private-path rejection.
JavaScript syntax is checked separately with Node.

Semantic assessment still depends on the human reviewer. The engine does not
provide autonomous entailment or broad answer synthesis. History scans immutable
snapshots and has no retention/cleanup UI. Selected sources that could not be parsed remain visible with unavailable metadata. No cloud, accounts or
telemetry are introduced.

## Troubleshooting

If Research cannot finish, check the private directory exists and is writable,
then check provider configuration. A missing optional provider never falls back
to paid search. If no passages appear, try another approved source or a clearer
query. If a run changed in another tab, reopen it from History. If a capture
changed, start fresh research and review again. If the port is busy, use --port.
See [verification methodology](verification-methodology.md) and
[local retrieval](local-retrieval.md) for engine behavior.

## Browser smoke record

A synthetic local provider and source were used in an external temporary folder.
Browser input reached the real research pipeline, displayed one passage and its
location, saved a human review, enabled Verify, displayed the expected fictional
TRUE verdict, and reopened the result from History. A script-like document title
was displayed as literal text. This tests the workflow, not real-world accuracy.
The browser download-event check timed out; both export responses were verified
through HTTP integration tests. No private source material or screenshots are
committed.

## Repeatable browser regression

Start the isolated fixture server from the repository root:

```powershell
python -B tests/ui_smoke_server.py
```

This server uses port 8001, a temporary external directory, an invented source,
and stubbed discovery/fetching. It does not read production research or call
external providers. Stop with Ctrl+C; restart it before each complete test.

In Codex's initialized browser tool, open http://127.0.0.1:8001 and bind that tab
to `tab`. Paste the function from `tests/ui_browser_smoke.js` into cua_repl,
then call `nodeRepl.write(await browserSmoke(tab))`. Do not evaluate it in the
webpage's console: it uses the browser automation API, not page JavaScript.
The script checks the review gate, inert source text, saved review, expected
fictional verdict, both export blob links and filenames, and history reopening.
It passed against the synthetic server. Export payload content is covered by
the Python HTTP tests. Browser download-manager/OS file persistence is not
asserted by this script.

After Export, the UI retains a Download report link for browsers that block the
automatic download. The link remains until another export or result render;
unused blob URLs are released when replaced. Exported files remain private and
must not be committed.

## Expanded free index

Use Research options → Refresh local source index to build or extend the private
500-document index. Each refresh has a two-minute scheduling budget; pending
URLs resume on the next refresh. Research summaries show indexed hosts,
pending URLs and stale-document counts. A first refresh does not guarantee
500 documents. See [crawler configuration](automatic-web-search.md#free-local-default).

## Manual URLs and keyword search

The browser defaults to Approved sources · automatic (free). Additional source
URLs are optional and supplement discovery; leaving the field empty still
searches the approved-site index. The former UI Manual URLs option has been
removed, and submissions from older tabs using that option are mapped to local
automatic discovery. The CLI --search-provider manual remains manual-only.
Restart the server and reload the browser after updating. Start a new run;
historical reports keep their original scope and failure records.

Page discovery and passage selection now share keyword scoring: stop-word
filtering, length normalization, term coverage, phrase/title weighting and
numeric-match preference. Use double quotes for an exact phrase. Broad synonyms,
translation and semantic relevance still require human judgment. An existing
review run whose selected candidate set changes under the new ranker must be
researched and reviewed again; old reviews are not silently reassigned.

Validation for this fix: 104 tests, 102 passed and two skipped. The bundled demo
retains all six answerable Hit@5 cases; this tiny fixture is not real-world
accuracy validation.
## Suggest and approve sources

Open Sources and submit an HTTPS website URL, publisher, and reason. Submission
only creates a pending suggestion; it does not fetch the website or add it to
approved search coverage. Open the original website yourself to assess identity
and relevance, then enter a reviewer name, classification, tier and official-site
status. Check the explicit approval confirmation and select Approve and add.
Reject suggestion leaves the host unapproved.

Approval permits only the exact hostname. Tier 2 is the default; selecting Tier 1
requires an explicit choice. Company classifications retain existing company
claim safeguards. Approval is not proof that every statement is true.

Suggestions and approval decisions are immutable private records under
TECH_RESEARCH_DATA_DIR. Approved additions reload on UI restart and apply to
future UI research; they do not modify the Git-tracked catalog or CLI policy.
Existing configured hosts cannot be overwritten through this workflow. Approval
is blocked while research runs to avoid changing its source policy mid-job.
A source-policy change causes the next local search to build a matching index.

This is a single-user local app: approval is an explicit human workflow, not a
separate authenticated administrator account. Other software with access as the
same OS user remains within the existing trust boundary. To change/remove a
previously approved addition, use a future managed policy-editing workflow;
this version intentionally provides no destructive cleanup button.

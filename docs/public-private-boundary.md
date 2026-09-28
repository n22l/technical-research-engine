> Verification extension: manual web captures, reviews, exact evidence, run manifests and Markdown reports also remain in the validated external directory. CLI output contains fixed status messages. No automatic production cache or credential discovery is used.

# Public/private boundary

Automatic discovery records queries, bounded titles/snippets, original URLs and policy decisions only in external private reports. Search snippets never become evidence. Only the documented Brave key environment variable is read, and its value is neither logged nor saved. Search queries are transmitted to the selected API provider; a private question file protects shell history but does not make an online query local-only. Offline mode makes no search calls.

## Public Git repository

Reusable software, public documentation, safe examples, tests, the evaluation framework, and explicitly synthetic demonstration data may be committed. The bundled fixture text, publisher labels, and source identifiers are invented and MIT-licensed. They are not production aerospace evidence.

## Private local data

Production research documents, copyrighted/local source extracts, editorial notes, unpublished research, real episode source collections, research outputs, and private evaluation sets belong outside every Git working tree. Keep rights and provenance records with those collections. Do not copy production text into tests, commits, issue bodies, logs, or public evaluation reports.

Existing private locations are not moved or renamed by this refactor. An existing `space-watch-private/` sibling may remain in place; any validated external directory can be selected. `.gitignore` is secondary protection, not permission to place private material inside Git.

## Configuration and output

Private mode uses `TECH_RESEARCH_DATA_DIR` if present, otherwise the legacy `SPACE_DATA_DIR`. An explicitly empty or invalid new value fails closed; it never silently switches to the legacy location. If both are absent, the command reports a fixed configuration error. Demo mode ignores both. No dotenv file is loaded and no default production location is discovered.

The existing directory is resolved and checked against the public repository, enclosing Git markers, bare repositories, and Git discovery. Input paths cannot escape the selected root or use symlinks, junctions, hard links, alternate data streams, or nested Git trees. Private results are exclusively created as `result-*.json` in that same root; terminal output contains no passages or absolute paths. These checks do not defend against a malicious concurrent process replacing directories.

See the [local guide](local-retrieval.md) for migration and commands. Use `--question-file` for sensitive questions to avoid shell history. Do not redirect private results into Git. Before publishing, inspect staged files for source text, personal paths, credentials, and generated outputs; use synthetic data for verification.

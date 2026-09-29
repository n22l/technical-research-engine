# Roadmap

| Phase | Current state and gate |
| --- | --- |
| A: Retrieval | Preserved local CLI and synthetic Hit@5. |
| B: Sources/citations | Policy, HTML/optional PDF and records implemented; broader extraction quality unmeasured. |
| C: Web research | Free local crawler/index is default and has a bounded live NASA check. Optional Brave and SearXNG adapters are mock-tested; their live integration remains unverified. |
| D: Verification | Human-reviewed stance/scope, dependencies and temporal corrections implemented; automatic semantics planned. |
| E: Reporting | JSON/Markdown and citation integrity implemented; substantive synthesis planned. |
| F: Evaluation | Synthetic regressions implemented; independently labeled held-out verification benchmark planned. |
| G: Multilingual | Original text and reviewed translation supported; aliases, cross-language retrieval and translation evaluation planned. |

Exactly one recommended next task: run a small labeled discovery benchmark against the free local index to measure authoritative-domain coverage and reveal registry gaps before expanding policy or automating semantic assessment. Keep captures and labels external. This task has not been automatically implemented.

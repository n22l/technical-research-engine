> Upgrade: tests/test_verification.py adds synthetic policy, citation integrity, dependency, temporal correction, plan/reuse, conflict, insufficiency, PDF-page, injection, private-output and network-boundary tests. These are regression tests, not a labeled accuracy benchmark. Existing Hit@5 below is unchanged.

# Evaluation plan

Automatic discovery now has synthetic API/selection tests in `tests/test_search_discovery.py`. `search_discovery.evaluate_discovery(selected_urls, expected_authoritative_domains, forbidden_domains, k)` computes expected-domain recall, labeled approved-URL precision and forbidden selections. The denominator for recall is unique expected domains; precision uses selected URLs at k. Empty expected sets or selected lists produce null for the relevant metric. These are fixture metrics, not production scores. API contract tests use mocked HTTP; no live-search accuracy is claimed.

**Status: Synthetic retrieval smoke evaluation implemented; broader protocol proposed.**

The current command evaluates six authored answerable fixture questions using expected-passage hit@5, plus two manually labeled unsupported questions for inspection only. These are not held-out research benchmarks. See the [local guide](local-retrieval.md) for exact scoring, commands, and a private ten-question workflow. Citation entailment, evidence-status classification, and generated-claim evaluation below remain future work.

## Implemented scoring

For each labeled answerable question, search returns at most five positive-score passages. A hit means the returned IDs intersect `expected_passage_ids`; hit rate at 5 is hits divided by answerable questions, or null if none are answerable. This is any-evidence hit@5, not precision@5, recall@5, or full evidence coverage. Manually labeled unanswerable cases retain returned IDs for inspection and never count as successes or failures in this rate.

The command does not evaluate answer accuracy, translation quality, claim support, contradiction resolution, hallucination detection, or unsupported-question detection. Search scores do not establish answerability. Evaluation only checks retrieval against the labels; label correctness requires human review.

## Planned evaluation

Future work may add precision@k, recall@k, MRR or other ranking metrics once the relevance labels justify them, plus citation correctness, evidence-to-claim consistency, unsupported-claim detection, and multilingual retrieval quality. None of these metrics is currently computed.

The objective is to measure whether the system retrieves relevant evidence and represents it faithfully. Persuasive prose is not evidence of correctness.

## Build a manually verified reference set

1. Freeze a small corpus version with source metadata and stable document/passage identifiers.
2. Draft research questions in English and Chinese, including same-language and cross-language retrieval, terminology variants, and entity aliases.
3. Include answerable, unanswerable, partial-answer, contradictory-source, and time-sensitive questions. Explicitly test announced targets versus demonstrated milestones.
4. Annotate relevant passages, required answer facets, bounded claims, evidence-status labels with rationales, and acceptable uncertainty or abstention.
5. Verify annotations against original sources, not generated summaries. Check translated passages against original-language qualifiers and units.
6. Record reviewer, review date, disagreements, and adjudication. Seek a second reviewer where practical; disclose when only one reviewer is available.
7. Separate development examples from held-out evaluation questions, keeping duplicates and closely related document versions together to reduce leakage.

Reference answers should allow multiple valid evidence passages. They should not imply that public sources reveal undisclosed operating costs or establish causal economic relationships.

## Planned assessment dimensions

| Dimension | Proposed assessment |
| --- | --- |
| Retrieval relevance | Judge ranked passages against annotated relevant evidence; consider precision/recall at a defined cutoff and rank-sensitive measures. |
| Citation correctness | Check document identity, version, location resolution, and whether the cited passage entails the associated assertion. |
| Claim–source consistency | Review dates, quantities, units, attribution, scope, and qualifiers; distinguish quotation, inference, and assumption. |
| Evidence-status classification | Compare labels with reviewed references; inspect per-class errors and confusion between targets, plans, tests, and achievements. |
| Unsupported claims | Decompose answers into atomic factual claims and count those lacking sufficient cited support. Review contradicted claims separately. |
| Multilingual terminology (initially English/Chinese) | Check translation fidelity, qualifier preservation, and retrieval across English/Chinese terminology variants. |
| Entity resolution | Evaluate correct matches and false merges among organizations, vehicles, stages, and program aliases. |
| Answer completeness | Compare covered evidence-backed facets with the annotated question requirements; do not reward speculative detail. |
| Abstention | Check whether the system recognizes insufficient evidence without refusing questions that the corpus can answer. |

Before experiments, define scoring units, retrieval cutoffs, denominators, and handling of partially supported claims. For unsupported-claim rate, use unsupported factual claims over all generated factual claims; report claim counts and abstentions separately so empty answers cannot appear successful.

The [aerospace status taxonomy](../src/domains/aerospace/taxonomy.md) is domain-specific, not a universal scoring requirement. Evidence status and factual support require separate annotations. A PLANNED claim can be fully supported as a statement of a plan without establishing that the planned event occurred.

## Experiment design

Start with a simple retrieval baseline. Assess retrieval independently before comparing semantic or cross-language variants. Later, evaluate generation using both manually selected evidence and actual retrieved evidence to distinguish generation errors from retrieval errors.

Version the corpus, annotations, parsing and chunking settings, model identifiers, prompts, filters, and retrieval configurations. Record translation method and review status. Keep held-out cases out of tuning, and manually inspect automated judgments rather than treating another LLM as ground truth.

Report performance by language, question type, source type, and evidence status where sample sizes permit. Small curated samples will limit generalization; document imbalance and missing coverage.

## Reporting policy

Publish numerical metrics only after the evaluation dataset and experiments exist. Reports should include dataset size, annotation procedure, scoring definitions, sample counts, actual results, failure examples, and limitations. The authored synthetic smoke evaluation is runnable; it is not a measured real-corpus performance baseline. Do not report unmeasured metrics or private results as public validation.

# Frozen answer-bearing retrieval benchmark v1

Document Hit@5 can succeed when a document's context paragraph appears but its
answer-bearing paragraph does not. Even passage Hit@5 can hide a misleading first
result. This benchmark measures those differences before any ranking change.

## Corpus and labels

`data/evaluation/answer-bearing-v1.json` contains 26 questions: 14 English and 12
Chinese, with 78 passages in a shared corpus. All programs, events and prose are
authored synthetic examples, not factual assertions about real aerospace programs.
There are no production captures, private editorial questions, external downloads,
credentials or copyrighted news excerpts. No network or API key is needed.

Labels were authored from the explicit relationships in each synthetic scenario,
before baseline scoring. They have not received independent human adjudication.
Answer-bearing includes explicit negative answers; it does not mean a claim is true.
Acceptable labels identify useful contextual evidence, not proof of the milestone.
Distractors explicitly fail a requested entity, component, time or milestone.
Other corpus passages are unlabeled and receive no usefulness credit. These are
deliberately sparse labels, not exhaustive relevance judgments across every pairing.
In the initial draft, ambiguous-case paragraphs duplicated other cases' asserted
events; those paragraphs were replaced by non-answering descriptions before freezing,
to avoid accidental unlabelled duplicate answers. No labels were adjusted to reward
the ranker. Future label corrections require a documented reason, version/checksum
change and reruns of both baseline and proposed ranker; never tune labels to scores.

| Failure category | Questions |
| --- | ---: |
| wrong_vehicle | 2 |
| wrong_component | 3 |
| wrong_country | 2 |
| wrong_time_period | 2 |
| planned_vs_demonstrated | 3 |
| recovery_vs_reflight | 2 |
| reflight_vs_routine_reuse | 2 |
| background_not_answer | 2 |
| entity_collision | 2 |
| partial_keyword_overlap | 2 |
| ambiguous_question | 2 |
| translation_or_language_variant | 2 |

The two `AMBIGUOUS` questions have no expected answer and are excluded from every
aggregate metric (24 scored cases). Their results remain visible for inspection;
this does not measure the engine's ability to detect ambiguity. Expected attributes
and rationales are annotations only and are never passed to the ranker.

## Reproduction and schema

From the repository root, with the normal project Python environment:

```powershell
python -B src/evaluate_benchmark.py
python -B -m unittest discover -s tests -p test_answer_benchmark.py -q
python -B -m unittest discover -s tests -q
python -B src/evaluate_passages.py
python -B src/evaluate_frozen.py
```

The evaluator checks the public fixture SHA-256 in `answer-bearing-v1.sha256`,
normalizing CRLF to LF so Git checkout settings do not alter the fingerprint.
It validates version, question IDs, language, status, answer attributes, categories,
source and passage IDs, label references, duplicates and disjoint labels. Ambiguous
cases must have no expected labels, and answerable cases must have at least one.
IDs cannot be filesystem paths. Errors omit input paths and source contents.

The top-level schema is `schema_version`, `passages`, `cases`; the fixture also
records provenance and a fixture version. Each passage has `passage_id`, `passage`,
`source` (`id`, `title`) and optional `location`. Each case has `id`, `language`,
`question`, `status`, `expected_answer_attributes` (`entity`, `component`,
`milestone`), the three passage-ID label lists, `failure_category` and `rationale`.
The checked-in JSON is the complete runnable example.

`--benchmark <external-file.json>` supports the same schema for an optional private
fixture. Keep that file outside Git. External runs print only counts and aggregate
metrics: no questions, passages, identifiers, paths, hashes or source metadata.
The command writes no output files. Do not redirect private metrics into the public
repository. The public default prints full synthetic diagnostics, including expected
text/rank (null when absent), top five texts with rank and label, and case category.
`needs_attention` marks expected rank other than 1, a non-useful top result, or any
labeled distractor in the first three. All cases remain available, not just failures.

## Scoring contract

The original baseline called `rank_passages` once per question over all 78 passages,
with a limit equal to corpus size, default two passages per document and deduplication
enabled. It does not use expected attributes or labels in retrieval. This isolates
ranking from crawl coverage, extraction, live index freshness and publisher access.
It does not exercise the local search provider's separate page weighting, UI or
verdict logic, and is not a real-world search success estimate.

All aggregate values are macro averages over the 24 answerable questions:

| Metric | Definition |
| --- | --- |
| Document Hit@5 | At least one expected passage's source document among the first five distinct documents in ranked passage order. Context from that document can produce a hit. |
| Passage Hit@5 | At least one expected passage in the first five returned passages. |
| Passage MRR | Reciprocal rank of the first expected passage across all returned results; zero if absent. |
| Top-1 useful precision | First result is expected or acceptable; empty results score zero. |
| Top-3 useful precision | Number of expected or acceptable results in first three divided by **3**, including empty slots as zero. |
| Distractor@3 | Count of explicitly labeled distractors in first three (0–3), averaged per question. |
| Distractor slot rate@3 | Distractor@3 divided by 3; empty slots contribute zero. |

Low distractor rate alone can reward returning nothing; read it alongside hit and
usefulness metrics. Unlabeled passages do not count as distractors or useful evidence.
Document Hit@5 follows the prior passage evaluation's derived-document concept;
it is not a separate measurement of the production document search provider.

## Baseline on unchanged ranker

Base revision: `21ad15edd984aa29960cd2eb6cd569756581808f`.

| New metric | Measured value |
| --- | ---: |
| Document Hit@5 | 1.000000 (24/24) |
| Passage Hit@5 | 0.958333 (23/24) |
| Passage MRR | 0.777778 |
| Top-1 useful precision | 0.625000 (15/24) |
| Top-3 useful precision | 0.513889 (37/72 slots) |
| Distractor@3 | 0.916667 (22/24) |
| Distractor slot rate@3 | 0.305556 (22/72 slots) |

Existing seven-case evaluation: document Hit@5, passage Hit@5, passage MRR and
sentence Hit@1 all 1.0. Existing ten-case frozen evaluation: lexical ablation 7/10,
subject-constrained 10/10. These smaller scores remain valid for their own fixtures.

Before changes, the full suite ran 148 tests: 145 passed, 2 skipped, 1 error in
`test_default_provider_has_no_api_key_requirement` (private-directory/Git validation
under its cleared environment). The benchmark does not weaken that test or alter
private-directory safeguards.

Final validation with `python -B -m unittest discover -s tests -q`: 157 tests,
154 passed, 2 skipped and the same 1 pre-existing error. All 9 new benchmark tests
pass. Both old evaluations retain their baseline results. `git diff --check` passes.
The full suite is therefore not green; the unrelated environment-dependent error is
disclosed rather than skipped or hidden.

## Concrete failure diagnostics

The table below records actual baseline results. Some categories are top-3 contamination
rather than top-1 failures; those are explicitly distinguished instead of claiming
every failure mode loses at rank 1.

| ID / category | Question | Top result (or identified contaminant) | Expected evidence / rank | Why it fails |
| --- | --- | --- | --- | --- |
| q01 wrong_vehicle | Did Aster One complete a booster reflight? | Aster Two completed a booster reflight; Aster One supplied its tracking equipment. | Aster One booster B7 completed a second flight, establishing reflight. / 2 | Mentions target as a contributor to another vehicle's flight. |
| q04 wrong_time_period | Did Iris recover its booster in 2020? | Iris recover booster: the 2020 summary describes a recovery performed in 2019. | Iris recovered its booster in 2020 after the coastal trial. / 2 | Publication year outranks the requested event year. |
| q05 planned_vs_demonstrated | Has the Marigold booster been reflown? | The Marigold booster will be reflown next year under the announced plan. | The Marigold booster completed its second flight; the same hardware was reflown. / 2 | Future plan outranks completed flight. |
| q07 reflight_vs_routine_reuse | Has Linden achieved routine booster reuse? | Linden achieved one booster reuse trial; routine service is a future objective. | Linden logs record routine booster reuse across twenty scheduled missions. / 3 | Single trial does not establish routine service. |
| q10 partial_keyword_overlap | Does Sorrel recover both stages? | Sorrel supports both crew and cargo; its stages carry equipment for these missions. | Sorrel recovers the lower stage, but expends the upper stage. Recovery applies to one stage only. / absent | “Both” refers to payload roles, not recovery scope; context still gives document Hit@5. |
| q15 wrong_country | 中国的银杏一级完成复飞了吗？ | 美国的银杏一级完成复飞，中国团队讨论了该结果。 | 中国的银杏一级完成第二次飞行，确认同一枚箭体复飞。 / 2 | Chinese mention belongs to the discussion team, not the flown vehicle. |
| q18 recovery_vs_reflight | 红杉一级是否验证了复飞？ | 红杉一级已验证回收，复飞试验尚未开展。 | 红杉一级已验证复飞：回收后的同一枚箭体再次发射。 / 3 | Explicitly unperformed reflight outranks completed reflight. |
| q24 translation_or_language_variant | 晨露发动机重复点火验证成功了吗？ | 晨露发动机重复点火验证计划已公布，试验尚未开始。 | 晨露发动机二次启动试验成功，验证了重复点火能力。 / 2 | Exact wording in a plan outranks a demonstrated synonym. |
| q25 wrong_component | Has Violet demonstrated upper-stage reuse? | Top is correct; rank 2: Violet demonstrated booster reuse; the upper-stage team observed the flight. | Violet upper-stage reuse has not been demonstrated; the upper hardware is discarded. / 1 | Wrong component remains a top-3 distractor. |
| q08 background_not_answer | Has Rowan completed booster reflight? | Top is correct; rank 2: Rowan booster reflight offers lower costs and faster turnaround in principle. | Rowan completed booster reflight when unit R4 launched for the second time. / 1 | General benefits remain a top-3 distractor, not a demonstrated event. |

## Original next-step proposal (implemented in the increment below)

Test a relationship-aware reranking step that aligns the requested entity, component
and milestone with the same event in a passage, retaining negation and planned versus
completed status. Measure it against this frozen corpus and inspect regressions;
do not use the benchmark's expected attributes as query-time hints. This is one
historical proposal; the following section records its implementation and measurements.

## Relationship reranking increment

The earlier section records the original proposal and lexical baseline. The increment
described here implements that proposal; `evaluate_benchmark.py` now exercises the
default reranker. `evaluate_relationships.py` compares the preserved
`rank_lexical_passages` baseline with the new default on the identical frozen input.
Both receive only query text and ordinary passage records, never expected attributes
or labels. Candidate generation and limitations are in [the ranking guide](retrieval-ranking.md).

Base revision: `d868347` (merged benchmark PR #19). The fixture and checksum are
unchanged: `6d714641ae818a461a1f25eda2dc36572dfbc571a84316ebd4c35c956edf4f8a`.

```powershell
python -B src/evaluate_relationships.py --experiments
python -B src/evaluate_benchmark.py
python -B src/evaluate_passages.py
python -B src/evaluate_frozen.py
python -B -m unittest discover -s tests -q
node --check src/ui_assets/app.js
node tests/ui_relationship_diagnostics.js
```

The comparison prints all answerable questions' old/new expected ranks and top-three
texts/labels, every metric regression, both language subsets and warm timing samples.
The ambiguous cases remain excluded from scored comparisons. Timing runs alternate
old/new order after warmup and include lexical candidate generation plus reranking,
not I/O, diagnostics serialization or network calls.

### Before / after, 24 scored questions

| Metric | Original lexical | Relationship reranker |
| --- | ---: | ---: |
| Document Hit@5 | 1.000000 | 1.000000 |
| Passage Hit@5 | 0.958333 | 1.000000 |
| Passage MRR | 0.777778 | 1.000000 |
| Top-1 useful precision | 0.625000 | 1.000000 |
| Top-3 useful precision | 0.513889 (37/72) | 0.555556 (40/72) |
| Distractor@3 | 0.916667 (22/24) | 0.958333 (23/24) |
| Distractor slot rate@3 | 0.305556 (22/72) | 0.319444 (23/72) |

The desired decrease in distractors **was not achieved**. This is a strong improvement
in first-result selection on this particular authored corpus, with a residual
top-three regression. It is not a perfect ranking or real-world accuracy claim.

### Required case inspection

| ID | Failure type | Old expected rank | New expected rank |
| --- | --- | ---: | ---: |
| q01 | Wrong vehicle participant | 2 | 1 |
| q04 | Report year versus event year | 2 | 1 |
| q05 | Plan versus completed reflight | 2 | 1 |
| q07 | Single trial versus routine reuse | 3 | 1 |
| q10 | “Both” payload roles versus stage recovery | Absent | 1 |
| q15 | Country discussed event versus performed event | 2 | 1 |
| q18 | Recovery/negative reflight versus completed reflight | 3 | 1 |
| q24 | Chinese demonstrated synonym versus exact plan wording | 2 | 1 |
| q25 | Upper stage versus booster | 1 | 1 |
| q08 | Specific reflight versus general benefits | 1 | 1 |

q13 also improves from rank 2 to 1. Every other answerable expected rank remains 1.
q10 now retrieves and prefers the actual stage-specific passage; it does not reward
an arbitrary occurrence of “both”. q18's negative reflight passage remains retrievable
and gets a negative-answer relevance diagnostic, never a successful-reflight stance.
The last two rows were already correct at rank 1; this increment does not claim to
have fixed their remaining distractor contamination.

### Every measured regression

No expected-passage rank, hit metric, MRR or useful-precision case regresses.
The sole per-case metric regression is **q20**, `木槿一级完成复飞了吗？`:

- Expected rank: **1 → 1**.
- Distractor@3: **0 → 1**; useful precision@3 stays **1/3**.
- The target-specific general-benefits paragraph `q20:d` enters rank 2, displacing
  an unlabeled other-program passage. Previously ranks 2 and 3 were `q13:d` and
  `q15:d`; now they are `q20:d` and `q13:d`.
- Entity alignment favors background about the requested entity over a completed
  event involving another entity. The background penalty is insufficient to push
  it beyond rank 3. Sparse labels do not count the old wrong-entity results as
  distractors for q20, so this regression must be read alongside unchanged usefulness.

This raises overall and Chinese distractor count/rate. English distractor metrics
are unchanged. No labels were reclassified to hide the regression.

### Language subsets

Each subset searches the same complete bilingual corpus. One ambiguous question
per language is excluded (13 English and 11 Chinese answerable).

| Metric | English before | English after | Chinese before | Chinese after |
| --- | ---: | ---: | ---: | ---: |
| Document Hit@5 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| Passage Hit@5 | 0.923077 | 1.000000 | 1.000000 | 1.000000 |
| Passage MRR | 0.756410 | 1.000000 | 0.803030 | 1.000000 |
| Top-1 useful precision | 0.615385 | 1.000000 | 0.636364 | 1.000000 |
| Top-3 useful precision | 0.538462 | 0.564103 | 0.484848 | 0.545455 |
| Distractor@3 | 0.923077 | 0.923077 | 0.909091 | 1.000000 |
| Distractor slot rate@3 | 0.307692 | 0.307692 | 0.303030 | 0.333333 |

### Weight experiment and latency

With variant candidate generation but relationship strength zero: Hit@5 is 1.0,
MRR 0.840278, top-1 usefulness 0.708333, top-3 usefulness 0.527778 and distractor
slot rate 0.305556. Strengths **0.25, 0.5, 1 and 2** all give the final aggregate
results above. The chosen 0.25 is the weakest tested nonzero strength achieving the
improvement; weights are shared across all entities, languages and questions.

On the local Windows host, five alternating warm runs of all 26 queries produced
median total ranking times of **0.528265 s lexical** and **1.177089 s relationship**:
about **20.3 ms → 45.3 ms per query**, or **2.23×**. These are wall-clock observations,
not a service-level guarantee; hardware/load and warm caches matter. The extra
candidate pass and clause analysis incur a real cost. No performance claim is made
for larger corpora or cold starts.

### Tests and integrity

Before changes, the full suite ran 157 tests: 154 passed, 2 skipped, and the known
`test_default_provider_has_no_api_key_requirement` environment error. A separate
logical commit preserves only OS process-launch variables while that test still
clears all application/API configuration and calls the real private-directory check.
No production safety check was bypassed.

Final `python -B -m unittest discover -s tests -q`: **175 tests, 173 passed,
2 skipped, no failures/errors**. The 18 added Python tests exercise unfamiliar
entity names, component conflicts, negative answers, plans, routine reuse, dates,
Chinese variants, inherited subjects, candidate limits, immutable input and
regression reporting. The offline Node diagnostic test and JavaScript syntax check
also pass. These UI checks validate message generation, not a live-browser walkthrough.

The old seven-case evaluation remains 1.0 on all four reported passage metrics.
The frozen ten-case evaluation remains 7/10 lexical and 10/10 subject-constrained.
Frozen v1 fixture bytes/checksum are unchanged. No private research, additional
sources, providers, external API, model, embedding or vector database was added.
Verification taxonomy, review gates, source authority and citation checks are unchanged.

### One recommended next task

Validate this reranker against an independently reviewed bilingual set of real
article passages, with comprehensive usefulness/distractor labels, before further
weight tuning. Perfect first-result performance on a known synthetic fixture cannot
establish production generalization. That validation is not implemented here.

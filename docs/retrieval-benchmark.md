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

The adapter calls unchanged `rank_passages` once per question over all 78 passages,
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

## Next ranking experiment (not implemented)

Test a relationship-aware reranking step that aligns the requested entity, component
and milestone with the same event in a passage, retaining negation and planned versus
completed status. Measure it against this frozen corpus and inspect regressions;
do not use the benchmark's expected attributes as query-time hints. This is one
proposed future experiment, not an implemented change or a promised improvement.

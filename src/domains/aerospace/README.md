> Runtime update: rules.py provides an optional reviewed-maturity guard. See docs/verification-methodology.md for the separate human-reviewed pipeline.

# Domain 01 — Aerospace Intelligence

The first research application is **reusable-rocket economics and launch cadence** for **US–China Space Watch / 中美航天观察**. English/Chinese synthetic retrieval examples are implemented; real-corpus validation remains separate and private.

Domain concepts include launch vehicles, launch sites, missions, payloads, recovery, reuse, orbital systems, agencies, commercial providers, launch cadence, and demonstrated versus planned capability. These are annotation and research concepts, not automated entity extraction.

The [milestone taxonomy](taxonomy.md) preserves the proposed aerospace status vocabulary. No runtime classifier or taxonomy loader exists. A demonstrated landing does not prove operational reuse; an announced target does not establish an achieved cadence. Separate events, plans, source assertions, and analyst assumptions. Economic analysis must expose units, time windows, missing costs, utilization, refurbishment, and demand assumptions; launch counts alone cannot establish profitability.

Candidate primary sources include NASA, FAA, CNSA, CMSA, relevant government records, and original aerospace organization/company publications. This is source-selection guidance, not an ingested collection or endorsement. Prefer original-language sources, review rights, and preserve dates and versions. See [source policy](../../../docs/data-sources.md) and the [domain model](../../../docs/domain-model.md).

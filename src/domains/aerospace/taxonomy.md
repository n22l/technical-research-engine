> Runtime update: rules.py now validates explicit review statuses and conservatively guards against unsupported maturity implications. It does not infer status from source prose.

# Aerospace milestone taxonomy

**Domain-specific annotation proposal; not a core requirement or an implemented classifier.**

These proposed labels describe the status of a specific claim or milestone as of a stated date, not the credibility of an entire organization.

| Status | Intended meaning |
| --- | --- |
| DEMONSTRATED | Evidence supports that the specified event or capability was demonstrated under stated conditions. |
| OPERATIONAL | Evidence supports routine or in-service use within the specified scope. |
| TESTING | The specified capability is undergoing tests; the intended outcome is not established. |
| PLANNED | A responsible organization has announced an intended activity or program. |
| TARGETED | A date, cadence, performance level, or other goal is stated as an aim rather than an achieved result. |
| PROPOSED | A concept or option has been put forward without evidence of a committed implementation plan. |
| DELAYED | Evidence explicitly supports a postponement relative to an identified earlier schedule. |
| CANCELLED | Evidence explicitly supports termination of the specified effort. |
| UNKNOWN | Available evidence is insufficient, ambiguous, or unresolved. |

Separating these states prevents a future target from being reported as an achievement or a test from being treated as routine service. An official announcement is evidence of what was announced; it is not automatically independent verification of the underlying capability.

Claims should be split when labels would otherwise overlap: a test demonstration and a future operational target are separate assertions. Missing updates alone do not establish delay or cancellation. Annotation rules will be refined before evaluation.

A future evidence-record implementation may load a domain-selected vocabulary. No taxonomy loader or status inference is implemented today.

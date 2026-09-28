# Source policy

`config/source-policy.json` seeds NASA, FAA, CNSA, SpaceX and Reuters exact hosts. A private `--policy` replaces the registry. Rules include `allowed`, `tier`, `type`, `publisher`, optionally `official`, `primary`, `include_subdomains`. Most-specific rules win; suffixes require a dot boundary. Hosted/lookalike subdomains are not automatically approved.

Tier 1 covers reviewed official/primary publishers; Tier 2 established professional reporting. Unknown blogs, forums, social posts, aggregators, snippets and Wikipedia are discovery-only and cannot support verdicts. This slice does not fetch rejected hosts; manually follow and qualify original authoritative sources.

Publisher authority is claim-specific. Company announcements are not independent performance proof, and reporting may merely repeat a release. The registry cannot establish page-level authenticity or truth. Human review and external rights records remain necessary; public access does not grant redistribution rights.

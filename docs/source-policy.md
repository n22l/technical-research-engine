# Source policy

`config/source-policy.json` seeds NASA, FAA, CNSA, SpaceX and Reuters exact hosts. A private `--policy` replaces the registry. Rules include `allowed`, `tier`, `type`, `publisher`, optionally `official`, `primary`, `include_subdomains`. Most-specific rules win; suffixes require a dot boundary. Hosted/lookalike subdomains are not automatically approved.

Tier 1 covers reviewed official/primary publishers; Tier 2 established professional reporting. Unknown blogs, forums, social posts, aggregators, snippets and Wikipedia are discovery-only and cannot support verdicts. This slice does not fetch rejected hosts; manually follow and qualify original authoritative sources.

Publisher authority is claim-specific. Company announcements are not independent performance proof, and reporting may merely repeat a release. The registry cannot establish page-level authenticity or truth. Human review and external rights records remain necessary; public access does not grant redistribution rights.

Automatic search results are discovery metadata only. Unknown hosts receive UNKNOWN / UNREGISTERED_SOURCE and remain unfetched pending human policy review; domain suffixes never confer trust. Explicit discovery-only and rejected rules are distinct from unregistered hosts. Approved candidates are selected by tier/primary status and publisher diversity before the existing fetcher performs DNS/TLS checks. API rank is not evidence strength. Both `company` and `company_official` source types retain the announcement-only guard. Other descriptive source categories and optional jurisdiction can be supplied in reviewed policy; no top-level-domain wildcard approval is introduced.

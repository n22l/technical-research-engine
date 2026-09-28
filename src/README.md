> New modules: verify.py composes verification_models.py, web_sources.py, verification.py and the optional aerospace guard. The local modules described below remain unchanged; see ../docs/architecture.md for the full current architecture.

# Source code

`research_search.py` contains the small, domain-independent standard-library ingestion, retrieval, metadata, private-path validation, and evaluation workflow. `space_search.py` preserves the previous command-line entry point. Neither generates answers or verifies claims.

[domains/aerospace/](domains/aerospace/README.md) contains domain guidance and a proposed human-annotation taxonomy, not a runtime plugin. See the [architecture](../docs/architecture.md) and [local guide](../docs/local-retrieval.md).

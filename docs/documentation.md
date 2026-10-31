[English](documentation.md) | [简体中文](documentation.zh-CN.md)

# Documentation language policy

English files keep their existing names; Simplified Chinese counterparts use
.zh-CN.md. Every release-facing README,presentation,architecture,reproduction,
acceptance,operations,roadmap and index document is listed in languages.json.
Each pair links to the other language. Update both in the same change.

Facts,capability state,scope/version pins,verification caveats and command blocks
must agree. Command blocks are intentionally identical,including variable names
and placeholders. The local checker enforces pair existence,reciprocal navigation,
exact shell blocks and valid local links; factual translation still needs review.

Historical reports,raw-log provenance,archives and specialized baseline reference
notes may retain their source language. The paired presentation/evidence ledger
summarizes them without changing originals or overstating validation. Personal
learning notes and secrets are never promoted just to complete translation.

```bash
python3 scripts/check_repository.py
python3 -m unittest discover -s tests -v
```

Offline checks do not validate the GPU deployment or the semantic accuracy of a
translation. Distinguish operator-observed runtime,historical source,generated
configuration and offline-tested public tools. Never mark a new GPU rerun passed
because a translated document or simulated test exists.

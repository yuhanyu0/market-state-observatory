# Market State Observatory 0.5.0-rc2

This candidate hardens feature semantics and private operator presentation. It adds no model, theme, provider, or trading capability.

## Corrected Contracts

- Feature values no longer imply evidence validity or model eligibility.
- Stale decision-derived calculations remain available only as forensic values.
- Range position uses a legal cumulative-session range and cannot exceed `[0,1]` when valid.
- Open baselines cannot create false breadth or ETF/basket agreement.
- Volume coverage is distinct from uncalibrated volume breadth.
- Next probes identify stale, missing, membership, event-provenance, and history incidents separately.
- Descriptive structure conflicts are not labeled as validated observer conflicts.
- REST reconciliation distinguishes expected asynchrony from material differences.

## Authorization

Candidate outputs remain retrospective, uncalibrated, unvalidated, and decision ineligible. Formal Data Shadow, Model Shadow, paper/live positions, and orders remain unavailable. The active `v0.4.5` capture release and Scheduler are unchanged.

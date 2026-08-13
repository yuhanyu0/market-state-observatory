# Product Requirements

## Product promise

Market State Observatory answers three questions quickly: is today's evidence
complete, what state can legally be estimated, and why is an action blocked?
It is a research observatory, not an execution product.

## Required outcomes

- The Today view exposes ET time, freshness, runtime phase, Data Shadow gate,
  timeline, six themes, gaps, health, and the evidence boundary.
- `DATA_READY`, `MODEL_ESTIMATED`, and `DECISION_ELIGIBLE` remain distinct.
- Every estimated state exposes lineage, uncertainty, invalidation, and next probe.
- Private runtime data never becomes a browser dependency.
- Empty, blocked, loading, and failed states explain their cause.
- Paper positions and real orders remain structurally unavailable.

## Success criteria

Users can answer the ten journeys in `USER_JOURNEYS.md` without reading the
methodology first. The application passes desktop/mobile browser tests, schema
validation, secret scans, publication audit, and the initial JavaScript budget.

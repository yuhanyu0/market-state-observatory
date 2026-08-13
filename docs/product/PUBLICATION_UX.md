# Publication UX

The browser consumes only the `public-data` branch overlay. Freshness is always
shown with the evidence date, and a partial rehearsal is labeled as partial.

Public state may include aggregate readiness, missingness, observer states,
conflicts, certificates, and experiment progress. It excludes raw or near-raw
SIP data, request identifiers, local paths, private Shadow artifacts, positions,
orders, and account information.

When the public snapshot is stale, the UI reports stale evidence. It never
silently substitutes a bundled sample as today's state.

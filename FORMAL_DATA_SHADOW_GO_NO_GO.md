# Formal Data Shadow Go / No-Go

## Decision: NO-GO

The scheduler-driven v0.4.3 Soak Day A completed all five core points and wrote
13,013,293 WebSocket messages with zero drops, but its immutable quality result is
`FAIL` (113/175, 64.57%). Offline forensics found that the old REST bundling rule
deleted rows when an exact-open completed bar did not yet exist or when provider
event time was milliseconds ahead of the collector clock. v0.4.4 corrected those
semantics, but an interrupted v0.4.3 run on 2026-08-17 then exposed a separate
Windows scheduler process-lifecycle defect. v0.4.5 fixes process-tree ownership
in a new release lane, but it has completed zero of the three required new
scheduler-driven PASS dates. Formal Data Shadow remains stopped.

## Passed

- Bounded hourly stream storage and one-million-message reconstruction.
- Exchange-calendar and 13:00 ET early-close schedule.
- Atomic cross-section evidence with freeze duration separated from market-event
  dispersion.
- Immutable release identity design and fail-closed mutable-tree boundary.
- Exact publication gates, lock, cleanup, retry, and single Pages trigger path.
- Schema-validated dynamic public UI with stale and invalid-state handling.
- Loopback private operator console, immutable labels, and local alerts.
- Python, Vitest, Playwright desktop/mobile, schema, secret, release-inspection,
  and dependency security checks at implementation-test level.

## Blocking Conditions

1. Build and review the immutable v0.4.5 wheel/venv without changing v0.4.3 evidence.
2. Install only the v0.4.5 rehearsal task after explicit operator approval.
3. Complete three new scheduler-driven full-day PASS rehearsals and the failure-injection checklist in
   `SOAK_TEST_PLAN.md`.
4. Review Scheduler start, WebSocket continuity, PIT-row and required-field completeness, disk
   budget, crash recovery, private operator state, and fail-closed publication.
5. Generate and independently review `SOAK_TEST_RESULTS.json`, then use the
   no-override promotion command to create the release-bound GO artifact.

Passing those operational checks permits a separate GO review. It does not start
Model Shadow, produce an investment action, or authorize any position or order.

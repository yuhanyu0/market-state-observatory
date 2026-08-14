# Release Notes 0.4.4

## Scope

This release is a point-in-time capture and runtime-durability correction. It adds
no model, Theme, investment rule, position, or order capability.

## Day A Boundary

The immutable v0.4.3 run `2026-08-14-bc1d37197bc0` remains `FAIL`. Its 72 missing
REST-derived rows were reproduced offline: 35 exact-open rows had no eligible
completed one-minute bar and 37 rows were rejected because provider quote time was
slightly ahead of the local REST completion clock. SPY, NVDA, SMH, and SOXX were
present at Alpaca; their exclusions came only from those old eligibility checks.

## PIT Contract

- The atomic WebSocket latest-state freeze happens before REST retrieval and is
  the primary known-at-PIT evidence.
- Every planned symbol receives a row. Quote, trade, minute bar, and VWAP each
  carry independent status and provenance.
- REST is backup, reconciliation, and completed-bar/VWAP support. Missing or
  disagreeing REST data cannot substitute for the frozen WebSocket state.
- At exact open, minute bar and VWAP are `NOT_YET_DEFINED`; the open point stays
  at 09:30.
- Provider event time, collector observed time, freshness, and clock-ahead
  diagnostics are retained separately. Already-received events are not rejected
  solely for sub-second provider clock lead.

## Runtime Durability

Completed UTC hours are frame-finalized, fsynced, atomically renamed, and given an
immutable manifest as the next hour begins. The current hour uses periodic durable
checkpoints; recovery truncates only uncheckpointed bytes and never modifies a
finalized hour. An independent heartbeat reports live stream, queue, disk, event,
and snapshot state during long waits.

## Promotion

v0.4.4 uses a new release identity and experiment lane. Three new scheduler-driven
PASS trading dates are required. Formal Data Shadow remains `NO-GO`; Model Shadow
is false; paper positions and real orders remain zero.

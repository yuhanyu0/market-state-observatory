# Operational Hardening Report

## Scope

Version 0.4.4 corrects point-in-time capture semantics and runtime durability
after the real scheduler-driven v0.4.3 Soak Day A. No model, Theme, scientific
target, investment action, position, or order capability was added.

## Immutable Day A Finding

Run `2026-08-14-bc1d37197bc0` remains `FAIL` at 113/175 (64.57%). Its WebSocket
archive contained all 35 symbols at every freeze and wrote 13,013,293 messages
with zero drops. Offline hash-checked raw evidence reproduced all 72 deleted REST
rows: 35 lacked an eligible completed bar at exact open and 37 had provider quote
time slightly ahead of the local REST completion clock. No provider call was made
for the audit and no Day A artifact was changed.

## v0.4.4 Outcomes

- The WebSocket latest-state cache is frozen before REST retrieval and is primary
  PIT evidence. Every planned symbol receives a row, including when REST fails.
- Quote, trade, minute bar, and VWAP have separate status, source, event time,
  observed time, and freshness. REST records reconciliation and derived fields;
  it cannot silently substitute for frozen primary evidence.
- Exact open remains 09:30. A completed 09:30 bar and cumulative VWAP are
  `NOT_YET_DEFINED`, not reasons to delete the quote observation.
- Quality reports observation, quote, trade, bar, and VWAP readiness separately.
  Direction and Transmission depend only on their declared input fields.
- Atomic `freeze_duration_seconds` is distinct from provider
  `event_time_dispersion_seconds`. Decision Transmission uses the decision freeze
  and cannot be poisoned by open or next-10:00 event dispersion.
- Completed UTC stream hours are finalized, fsynced, atomically renamed, and
  manifested as the next hour starts. The open hour has periodic durable
  checkpoints and restart truncates only uncheckpointed bytes.
- An independent heartbeat reports runtime phase, next event/countdown, actual
  WebSocket connection, last-message age, symbol/message counts, queue/backpressure,
  drops, disk usage, and last completed snapshot during long waits.
- Operator-facing JSON uses normalized semantic keys and parses in Windows
  PowerShell 5.1. Native `T`/`t` keys remain confined to private stream evidence.

## Acceptance Evidence

- Python: 105 tests passed; Ruff and strict mypy passed for 52 source files.
- Schema/public validation: 25 schemas and 101 public objects passed.
- Vitest: 4 passed; Playwright desktop/mobile: 12 passed; React production build
  and nine-route link check passed.
- Windows PowerShell 5.1.26100.9168 and PowerShell 7.6.4 compatibility/scheduler
  safety suites passed.
- Stream load: 35 symbols, 1,000,000 messages, 8 chunks and 8 manifests,
  1,000,000 reconstructed, zero loss, zero duplicates/drops, 99 backpressure
  events, 16 files, and 10,592,838 compressed bytes.
- Automated tests cover early finalization, current-hour checkpoint recovery,
  immutable finalized-hour hash, heartbeat progression, exact-open semantics,
  post-freeze rejection, REST disagreement, and decision-scoped Transmission.
- Publication audit, credential/secret scan, and schema validation passed.

## Remaining Boundary

The v0.4.4 scheduler is not installed. v0.4.4 has zero scheduler-driven PASS
trading dates and still requires three. Formal Data Shadow is `NO-GO`, Model
Shadow remains false, and paper/real position and order counts remain zero.

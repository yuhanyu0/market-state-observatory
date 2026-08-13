# Operational Hardening Report

## Scope

Version 0.4.1 hardens the existing data-only Observatory. No model, Theme,
position, order, scientific target, or Formal Data Shadow run was added.

## P0 Outcomes

- WebSocket messages update an in-memory latest-state cache and a bounded queue.
  The durable stream is hourly `NDJSON.zst` plus one immutable manifest per hour;
  full-envelope debug storage defaults to false.
- XNYS sessions come from `exchange-calendars`. Open, midpoint, close minus 30,
  close minus 15, and close are sorted from the exchange schedule. The 2026-11-27
  13:00 ET close produces 12:30 and 12:45 preclose points.
- Each scheduled observation freezes all symbols under one cache lock and records
  start/completion, earliest/latest event times, skew, and REST backup hash.
  Skew above five seconds blocks Transmission readiness.
- Formal execution requires a versioned wheel, dedicated venv, dependency lock,
  release manifest, and verified hashes. A changed wheel or universe starts a new
  experiment lane. Scheduled Task no longer invokes mutable source code.
- Publication requires every formal, process, quality, eligibility, schema,
  secret, forbidden-path, and zero-position/order gate. It uses a lock, stale
  worktree cleanup, and bounded push retry. No explicit duplicate Pages dispatch
  remains.
- Public operational UI content is loaded from Zod-validated JSON. It displays
  evidence time/age semantics, stale/degraded/failed state, runtime phase, next
  event, action required, evidence grade, and rehearsal/formal labels. Unknown
  contracts display `Public state invalid`.
- The operator console binds only to `127.0.0.1`. It shows scheduler/runtime/
  WebSocket/quality/log/lineage/alert state and exposes immutable quality recheck
  plus fail-closed publication retry.
- Label settlements append immutable ledger records linked to source run and
  snapshot hashes; they never mutate the source run and are idempotent.
- Windows Toast is the preferred best-effort notification path. Every alert is
  also persisted in a private immutable alert ledger.
- CI can generate a source zip, Windows bootstrap zip, and `SHA256SUMS`. Packaging
  uses tracked-file allowlisting, excludes private/runtime/build artifacts, and
  enforces a source archive below 5 MB. License status remains All rights reserved.

## Acceptance Evidence

- Python: 77 passed.
- Vitest: 4 passed.
- Playwright: 12 passed across desktop and mobile; accessibility checks passed.
- Static checks: Ruff and strict mypy passed.
- Public JSON: all 101 JSON objects validated against 22 explicit schemas.
- Security: publication audit and credential/secret scan passed; npm audit found
  zero vulnerabilities.
- Stream load: 35 symbols, 1,000,000 messages, 8 chunks, 8 manifests, 16 files,
  1,000,000 messages reconstructed, zero drops, debug false, no credential match.
- Backpressure was exercised 99 times with no message loss. Compressed storage was
  12,659,923 bytes under a 512 MiB test budget.
- Clean release inspection passed; the final source zip was 2,008,956 bytes,
  below the 5 MB ceiling, with a separate Windows bootstrap zip and SHA256SUMS.
- Early close, stale UI, crash-lock cleanup, failed-quality publication rejection,
  cross-section skew degradation, immutable settlement, and loopback binding are
  automated tests.

## Remaining Boundary

The runtime has not completed a full exchange session from the frozen production
wheel under Windows Task Scheduler. This report therefore does not authorize
Formal Data Shadow, Model Shadow, paper positions, or real orders.

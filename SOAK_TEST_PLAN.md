# Soak Test Plan

## Purpose

Prove the frozen v0.4.1 data-only runtime over a complete XNYS session before any
Formal Data Shadow day can be considered.

## Preconditions

1. Build the release from a clean committed tree with
   `ops/windows/build_runtime_release.ps1`.
2. Verify wheel, dependency, collector, schema, universe, membership, and config
   hashes from `release_manifest.json`.
3. Run the frozen formal dry-run and scheduled-task smoke test.
4. Keep the session in rehearsal mode; positions and orders remain zero.

## Full-Day Rehearsal

Capture calendar-derived open, midpoint, close minus 30 minutes, close minus 15
minutes, and close. Keep the SIP WebSocket connected for the full session. Verify:

- all 35 frozen symbols are present at each atomic cross-section freeze;
- quote age is at most 60 seconds and event timestamps are not in the future;
- no missed point is reconstructed;
- hourly chunk and manifest counts remain bounded;
- disk use stays below the configured 2 GiB daily budget;
- REST backup hashes and scheduled snapshot bundles reconstruct each fixed point;
- cross-section skew is recorded and Transmission is degraded when above limit;
- crash restart resumes only incomplete points and never overwrites evidence;
- rehearsal fails publication and never advances the 20-day gate;
- local alerts fire for an intentionally induced disconnect and quality failure;
- operator console remains reachable only at `127.0.0.1`.

## Failure Injection

Run one rehearsal each for credential rejection, WebSocket disconnect, stale lock,
missing quote, late observation, quality failure, publication crash, and stale
public state. Preserve every failed run; do not repair it by backfill.

## Exit Criteria

All fixed observations captured, quality reproducible, secret and schema scans
passing, no overwritten artifacts, no private public-data fields, no positions or
orders, and a reviewed operator record. A single failed criterion keeps the
system at NO-GO.

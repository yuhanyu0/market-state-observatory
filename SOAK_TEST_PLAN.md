# Soak Test Plan

## Purpose

Prove the frozen v0.4.4 data-only runtime over at least three complete,
scheduler-driven XNYS sessions before any Formal Data Shadow day can be considered.

## Preconditions

1. Build the release from a clean committed tree with
   `ops/windows/build_runtime_release.ps1`.
2. Verify wheel, dependency, collector, schema, universe, membership, and config
   hashes from `release_manifest.json`.
3. Install only `MSO-Daily-Rehearsal` and run its registered-action smoke test.
4. Keep every session in rehearsal mode; positions and orders remain zero.

## Full-Day Rehearsal

Capture calendar-derived open, midpoint, close minus 30 minutes, close minus 15
minutes, and close. Keep the SIP WebSocket connected for the full session. Verify:

- all 35 frozen symbols are present at each atomic cross-section freeze;
- all planned symbols have explicit PIT rows and all required Direction quotes
  have freshness age at most 60 seconds;
- no missed point is reconstructed;
- each completed UTC hour is immutable before session shutdown and the open hour
  has a current durable checkpoint;
- disk use stays below the configured 2 GiB daily budget;
- REST backup hashes and scheduled snapshot bundles reconstruct each fixed point,
  with REST disagreement recorded rather than substituted;
- freeze duration and event-time dispersion remain distinct, and Transmission is
  degraded only by the relevant decision freeze duration or missing required fields;
- crash restart resumes only incomplete points and never overwrites evidence;
- rehearsal fails publication and never advances the 20-day gate;
- local alerts fire for an intentionally induced disconnect and quality failure;
- the independent heartbeat advances during waits and the operator console remains
  reachable only at `127.0.0.1`.

## Failure Injection

Run one rehearsal each for credential rejection, WebSocket disconnect, stale lock,
missing quote, late observation, quality failure, publication crash, and stale
public state. Preserve every failed run; do not repair it by backfill.

## Exit Criteria

At least three distinct trading dates must have all fixed observations captured,
quality reproducible, zero future timestamps, backfills, message drops,
positions, and orders, passing secret/boundary/settlement/publication-isolation
checks, and a frozen scheduler version. A reviewed `SOAK_TEST_RESULTS.json` must
reference and hash every immutable rehearsal run and quality file. A single
failed criterion keeps the system at NO-GO. The v0.4.3 Day A failure is permanent
evidence and cannot count as one of the three v0.4.4 PASS dates.

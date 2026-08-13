# Full-Day Data Shadow Automation

## Purpose

Convert the successful afternoon rehearsal into a repeatable, unattended point-in-time collection process without weakening the evidence contract.

## Daily operating sequence

```text
09:25 ET  start collector daemon and authenticate SIP stream
09:30 ET  freeze open snapshot
12:00 ET  freeze midday snapshot
15:30 ET  freeze first pre-close snapshot
15:45 ET  freeze final decision snapshot
16:00 ET  freeze provider session-close diagnostics
next day  capture open, 10:00 and 15:45 labels
then      build immutable quality card and gate result
```

## Credential handling

The scheduler must not store Alpaca credentials in repository files, task arguments or logs. Use a local secret mechanism such as Windows Credential Manager or a DPAPI-protected local store. The public repository only contains interfaces, redacted status and validation logic.

## Process model

A single daily process is preferred over independent scheduled REST commands:

1. Start before the first observation point.
2. Open the SIP stream and audit subscriptions.
3. Maintain an append-only local raw stream.
4. Freeze exact observation snapshots at scheduled times.
5. Use REST snapshots only as an independently hashed audit fallback.
6. Fail closed if the clock, feed, quote freshness or symbol coverage contract fails.
7. Never reconstruct a missed observation.

## Graduation gates

### Full automated rehearsal

Must complete all planned same-day points with no future timestamps, no backfill, explicit SIP lineage and public/private publication audit pass. It still does not count toward the 20-day gate.

### Formal Data Shadow

Begins only after a separate run ID and pre-registered configuration are frozen. Data Shadow remains capture-only and creates no model actions or positions.

### Model Shadow

May begin only after the formal data-quality gate is met and the transparent Direction model is frozen. Transmission, Episode and Playbook are evaluated as separate ablations.

## Public publication

Only a redacted `PublicRehearsalSummary` or `PublicationStatus` may be copied into this repository. Raw provider payloads remain private and local.

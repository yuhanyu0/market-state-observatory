# Day 0B Alpaca SIP Rehearsal — 2026-08-10

Experiment ID: `day0b-alpaca-sip-20260810-03`
Research grade: infrastructure rehearsal
Formal Data Shadow contribution: **0 days**
Model Shadow / paper positions / real orders: **not created**

## Direct result

The afternoon point-in-time chain passed.

- Planned public-audit records: **740**
- Valid captured records: **666**
- Intentionally missed early-window records: **74** (`09:30`, `12:00`)
- Pending after session close: **0**
- Future timestamps: **0**
- Backfilled observations: **0**
- Explicit SIP lineage: **all records**
- Credential values persisted: **false**

At the 15:45 checkpoint, all six frozen themes had complete data inputs for both the Direction and Transmission layers:

- Direction data-ready: **6 / 6 themes**
- Transmission data-ready: **6 / 6 themes**
- Episode ready: **0 / 6 themes**
- C2 ready: **0 / 6 themes**

Every theme had complete minute-bar coverage, valid point-in-time VWAP, full frozen constituent coverage and a frozen prospective membership snapshot. The maximum quote age was **13.401112 seconds at 15:30** and **9.967655 seconds at 15:45**, both inside the frozen 60-second limit.

## Why this matters

This is the first completed rehearsal in which the system demonstrated, for all frozen themes, that it can collect the point-in-time market evidence needed by the Direction and Transmission layers without future timestamps or reconstruction.

The layered readiness contract also behaved correctly:

1. At 15:30, Direction and Transmission remained blocked because the 15:45 evidence point had not arrived.
2. At 15:45, all six themes became data-ready.
3. Episode remained blocked because one afternoon does not create a legal sequential state history.
4. C2 remained blocked by design and did not prevent ETF-level readiness.

## What this does **not** prove

- `direction_data_ready=true` does not mean a theme had positive Direction.
- `transmission_data_ready=true` does not mean broad transmission actually occurred.
- A working capture chain does not prove predictive information or investment alpha.
- This partial rehearsal does not count toward the 20-day formal Data Shadow gate.
- No position or order was generated.

## Next milestone

Run a full automated rehearsal that begins before 09:30 and captures all frozen observation points, including 09:30 and 12:00. After that full chain passes, begin formal Data Shadow as a separate, immutable run series.

## Public/private boundary

This report includes only redacted aggregate readiness metrics. It excludes credentials, account identifiers, raw provider payloads, per-security private response files, positions and orders.

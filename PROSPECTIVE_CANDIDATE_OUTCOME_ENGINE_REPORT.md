# Prospective Candidate and Outcome Engine Report

Branch: `feature/v0.5.1-prospective-candidate-outcome-engine`  
Frozen parent: `b91308d70d318567697dd4019648d47dc81c61de`  
Release: `v0.5.1-rc1`, candidate only, not activated.

## Historical closure

The one-time H2 diagnostic used 18,703 raw/unadjusted theme-date records across 3,654 dates and six themes. It ranked 5-day relative momentum and used D1 only as a frozen zero-threshold veto.

At 10 bps per active leg, top1-minus-bottom1 produced:

| Horizon | Dates | Mean net spread | Bootstrap 95% CI | Mean Spearman |
|---|---:|---:|---:|---:|
| next open to 3d close | 3,486 | -8.60 bps | [-18.79, +1.99] bps | 0.0037 |
| next open to 5d close | 3,486 | -13.48 bps | [-28.00, +0.36] bps | 0.0053 |

This is not a clear robust after-cost cross-theme result. `H2_MODEL_MINING_CLOSED=true`; no retired H2 model is reactivated.

## Existing H1 labels

The three frozen exact-PIT rehearsal runs contain 18 theme-run records. The legal sidecar audit settled 27 outcomes and left 81 `NOT_SETTLED`; no unavailable price was reconstructed. These outcomes are `rehearsal_research_only`, are not official strategy evidence, and count toward neither Formal nor Model Shadow gates.

## Candidate contract

`CANDIDATE_SIGNAL.json` is written once and hashes its protocol, disposition registry, source run, source snapshot, and exact source artifacts. Preclose manifests exclude close, quality, and future-run inputs. Postclose signals explicitly set earliest legal execution to the next trading-day open.

The ten frozen arms are B0 zero, B1 ETF 5-day momentum, B2 SPY-relative momentum, D0 PIT control, D1 PIT core, D1 PIT full, T0 PIT, D1 core plus T, D1 core plus unsigned Theme Radar attention, and D1 core plus T plus E0. Missing range or volume breadth does not block D1 core; both remain full-only.

B1 becomes estimable only after six immutable official-close observations exist in the same experiment lane. Preclose candidates use prior sessions only, and every historical RUN/close input is hashed in the candidate manifest.

## Outcome contract

`PROSPECTIVE_SIGNAL_LEDGER.ndjson` and `PROSPECTIVE_OUTCOME_LEDGER.ndjson` are append-only. Every settled label records event and observed timestamps, provider/source, source run/snapshot hash, settlement run/version, and safety flags. Each settlement invocation writes a deterministic immutable `SETTLEMENT_MANIFEST.json`; a repeated run id returns the existing bytes.

For long diagnostics, entry is the post-candidate SIP ask and exit is the future SIP bid. For short diagnostics, entry is the post-candidate SIP bid and cover is the future SIP ask. Mid-to-mid is reported only as a gross diagnostic. Fixed-cost results use 0/5/10/15/25/50 bps.

## Gates and UI

Gates count distinct valid trading dates, never theme rows: 10 is operational/coverage only, 20 permits early failure pruning only, 40 is the first paired ablation, and 60 is final research disposition review. Positive promotion before 60 is forbidden.

The loopback-only Operator Console adds Candidate Shadow, Pending Outcomes, Settled Outcomes, Accuracy, Timing, and Model Graveyard. It labels evidence as descriptive, retired, prospective candidate, pending, settled, insufficient, or Model Shadow disabled. Candidate output is never presented as a recommendation.

## Safety boundary

`prospective_unvalidated=true`; `decision_eligible=false`; `counterfactual_only=true`; `paper_positions=0`; `real_orders=0`. The implementation contains no broker order object or portfolio mutation and creates no Formal or Model Shadow authorization.

## Verification

- Python: 155 tests passed; Ruff, Mypy, 47 schemas/101 validated objects passed.
- Web: 4 Vitest tests and 18 desktop/mobile Playwright tests passed; ESLint and production build passed.
- Windows: process compatibility, scheduler safety, runtime lifecycle, and candidate-task `WhatIf` passed on Windows PowerShell 5.1 and PowerShell 7.6.4.
- Secret scan and publication audit passed. The candidate task remained absent; Formal runs, Model Shadow files, positions, and orders remained zero.

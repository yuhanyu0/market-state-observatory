# Observation-to-Decision Foundation

Status: `v0.5.0-rc1` candidate on a non-production feature branch.

This release candidate adds a private read-only analysis sidecar around completed immutable capture runs. It does not alter the active `v0.4.5` capture release, Scheduler action, universe, or completed run evidence.

## Execution Boundary

| Mode | Completed-run facts | Candidate replay | Validated model | Position or order |
| --- | --- | --- | --- | --- |
| `OBSERVATION_ONLY` | yes | no | no | no |
| `CANDIDATE_REPLAY` | yes | retrospective, unvalidated | no | no |
| `MODEL_SHADOW` | only with a valid promotion artifact | yes | paper-only | real order unavailable |
| `PAPER_LIVE` | unavailable | unavailable | unavailable | unavailable |

`MODEL_SHADOW` is currently blocked. `PAPER_LIVE` cannot be enabled by configuration.

## Evidence Flow

1. The compiler reads `RUN.json`, `DATA_QUALITY.json`, frozen membership, point manifests, declared snapshot bundle hashes, and optional label evidence.
2. It writes deterministic feature, provenance, and feature-quality ledgers outside the source run.
3. Observation reports separate evidence validity, facts, descriptive structure, candidate status, unknown claims, next probes, health, and authorization.
4. Candidate replay may invoke D0/D1/D2 Direction, transparent Transmission, E0/E1/E2 Episode candidates, candidate Fragility, conflicts, NextProbe, certificates, and counterfactual playbooks.
5. Every candidate remains `validated_model=false` and `decision_eligible=false`.

Open-point minute bars and VWAP marked `NOT_YET_DEFINED` become `NOT_APPLICABLE`; they do not reduce later readiness. Event, observed, and maximum-data timestamps are retained on every feature, and a source event later than its observation is rejected.

## Candidate Stacks

Direction configs are frozen under `config/candidates/`:

- `D0_SIMPLE_RELATIVE`
- `D1_TRANSPARENT_MULTI_FEATURE`
- `D2_CALIBRATED_PROBABILISTIC`

All are `NOT_CALIBRATED`. D2 emits no validated probability. Full-sample outcome performance is never used to choose thresholds.

Transmission reports input readiness, candidate state, and validated state separately. Episode E0 is a sequential interpretable state machine, E1 is a BOCPD candidate, and E2 is a disabled HSMM plugin contract. Insufficient history returns `not_estimable`.

Theme Radar remains an isolated unsigned external benchmark. It is not required for a decision, cannot select a theme, and cannot select a playbook.

## 2026-08-18 Acceptance

The compact fixture preserves the completed run's point manifests, frozen membership, quality artifact, stream-health artifact, and source hashes. The compiler reconstructs 864 point-in-time feature records.

The decision observation has 35 stale primary quotes, approximately 141 to 162 seconds old. The required report headline is:

`NO DECISION / PRIMARY FEED FRESHNESS FAILURE`

Direction input readiness and Transmission input readiness are blocked. Candidate certificates are `DATA_BLOCKED_NO_DECISION`; no valid 15:45 Direction certificate is formed.

## Daily Sidecar

`ops/windows/run_daily_report.ps1` reads only a completed run with `DATA_QUALITY.json`, waits a bounded interval if capture is active, strips market-data credentials from its child environment, requires no network, and writes only under the private analysis tree. It verifies that the source-run hash tree is unchanged.

The `MSO-Daily-Report` installer defaults to 16:15 ET on weekdays and verifies the source date against XNYS. Installation requires an explicit reviewed `-WhatIf` flow and is not performed by this sprint.

## Publication Boundary

Detailed observation reports, ticker-level contributors, incidents, candidate certificates, and experiment results remain private. The public site may contain only sanitized quality status, methods, synthetic certificates, and explicitly approved aggregate metrics. Raw SIP evidence, local paths, credentials, positions, orders, and investment recommendations are forbidden.

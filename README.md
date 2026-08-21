# Market State Observatory

> Development candidate: `v0.5.1-rc1` Prospective Candidate and Outcome Engine. The active capture runtime remains frozen at `v0.4.5`.

**Auditable evidence-state infrastructure for incomplete market observers.**

Market State Observatory is an independent public research product. It does **not** replace or modify
[`yuhanyu0/theme-radar-log`](https://github.com/yuhanyu0/theme-radar-log),
and Theme Radar can enter only as an isolated, unsigned benchmark observer.

- Product: https://yuhanyu0.github.io/market-state-observatory/
- Repository: https://github.com/yuhanyu0/market-state-observatory

```text
Private point-in-time collection
  -> evidence quality
  -> observer estimates
  -> conflicts and next probe
  -> State Certificate
  -> prospective validation
```

## Product boundary

`DATA_READY`, `MODEL_ESTIMATED`, and `DECISION_ELIGIBLE` are separate states.
Missing evidence produces `DATA_BLOCKED_NO_DECISION`; readiness never becomes a
positive Direction estimate. The runtime contains no broker adapter and cannot
create paper positions or real orders.

## Architecture

- `src/market_state_observatory/runtime/`: private, data-only Alpaca SIP runtime.
- `src/market_state_observatory/publication/`: fail-closed public projection.
- `web/`: Vite + React + TypeScript product interface.
- `public/data/`: the only repository path for generated public JSON.
- `schemas/`: Draft 2020-12 evidence contracts.
- `ops/windows/`: DPAPI credentials, runtime, scheduler, and publisher tooling.
- `labs/`: disabled and removable research modules.

Private provider data and secrets live outside Git at:

```text
%LOCALAPPDATA%\MarketStateObservatoryRuntime\
```

Raw SIP responses, exact request lineage, credentials, account data, positions,
orders, and private Shadow artifacts cannot cross the publication firewall.

## Current evidence

The redacted 2026-08-10 Day 0B SIP rehearsal captured 666 of 740 planned
records, missed the already-past 09:30 and 12:00 observations, recorded no
future timestamps or backfills, and counted as 0 of 20 formal Data Shadow days.
It is infrastructure evidence, not strategy evidence.

Formal Data Shadow has not started. Model Shadow has not started. Paper
positions and real orders are both zero.

The v0.5.1 candidate release can freeze counterfactual Theme ETF candidates
before their outcomes and settle later SIP labels without changing source runs.
It is not active, cannot emit broker order objects, and does not authorize Model
Shadow. The optional 15:46 preclose task exists only as a reviewed `-WhatIf`
preview until it is separately installed.

## Development

```bash
make setup
make dev
make test
make audit
make build
make release
```

Windows equivalents are `scripts/setup.ps1`, `dev.ps1`, `check.ps1`,
`publish.ps1`, and `release.ps1`. The local product URL is printed by Vite,
normally `http://127.0.0.1:5173/`.

## One-time Windows setup

```powershell
.\ops\windows\setup_alpaca_credentials.ps1
.\ops\windows\setup_github_auth.ps1
.\ops\windows\build_runtime_release.ps1
.\ops\windows\select_runtime_release.ps1 -ReleaseRoot '<reviewed release path>' -Select
.\ops\windows\install_scheduled_tasks.ps1 -Mode rehearsal -Install
```

The first command initializes the external runtime and stores Alpaca credentials
with current-user Windows DPAPI. The second never displays a GitHub token. The
third builds a versioned wheel, dedicated virtual environment, dependency lock,
and immutable experiment lane without changing the selected runtime or scheduler.
The fourth explicitly selects the reviewed release. The fifth installs `MSO-Daily-Rehearsal`
against that frozen release and first runs an offline dry-run. Formal scheduler
installation is fail-closed until three complete scheduler-driven rehearsals
produce a release-bound GO promotion artifact. An authorized successful formal
day then publishes only derived, redacted state to
`public-data`; rehearsal and failed-quality runs never publish.

Use the identity-scoped lifecycle command before release changes or maintenance:

```powershell
.\ops\windows\stop_runtime.ps1 -TaskName MSO-Daily-Rehearsal
```

The v0.4.5 launcher owns the frozen Python tree through a Windows Job Object. A
Task Scheduler stop or launcher crash closes the Job and terminates every runtime
descendant; the stop command never targets Python by process name.

Private operator state is available only on loopback:

```powershell
.\ops\windows\run_operator_console.ps1
```

## Private completed-run analysis

The release candidate can build a deterministic sidecar without modifying its source run:

```powershell
python -m market_state_observatory build-daily-report `
  --run C:\path\to\completed-run `
  --output C:\private\analysis\run-id `
  --mode OBSERVATION_ONLY
```

Every compiled feature separates calculation existence, evidence quality, and model-input eligibility. `CANDIDATE_REPLAY` is retrospective and unvalidated. `MODEL_SHADOW` requires a separate promotion artifact, and paper/live execution remains unavailable. See [`OBSERVATION_TO_DECISION_FOUNDATION.md`](OBSERVATION_TO_DECISION_FOUNDATION.md).

## Validation

```bash
pytest
npm test
ruff check src tests scripts
mypy src
python scripts/validate_repo.py
python scripts/audit_publication.py
python scripts/check_secret_patterns.py
npm run build
npm run test:e2e
python scripts/run_stream_load_test.py --messages 1000000
python scripts/build_release_packages.py
```

See [`OPERATIONS_RUNBOOK.md`](OPERATIONS_RUNBOOK.md),
[`docs/PUBLICATION_FIREWALL.md`](docs/PUBLICATION_FIREWALL.md), and
[`docs/product/PRODUCT_REQUIREMENTS.md`](docs/product/PRODUCT_REQUIREMENTS.md).

No open-source license has been selected. All rights remain reserved; see
[`LICENSE_DECISION.md`](LICENSE_DECISION.md).

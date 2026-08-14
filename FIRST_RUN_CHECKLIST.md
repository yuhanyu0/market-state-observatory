# First Run Checklist

## 1. Alpaca credential

- [ ] Run `ops\windows\setup_alpaca_credentials.ps1`.
- [ ] Confirm the printed path ends in
  `MarketStateObservatoryRuntime\secrets\alpaca.credential.xml`.
- [ ] Confirm the output says DPAPI current-user only and PRESENT/PRESENT.
- [ ] Run `ops\windows\test_alpaca_credentials.ps1`.
- [ ] Confirm the feed is explicitly `sip`; no credential value is printed.

## 2. GitHub authentication

- [x] GitHub CLI 2.97.0 is installed.
- [x] GitHub web authentication is complete for `yuhanyu0`.
- [x] Authentication uses the system keyring; no token value was requested or
  written by this project.
- [x] Git credential helper is not plaintext `store`.

## 3. Scheduled task

- [ ] Explicitly select the reviewed frozen release with `select_runtime_release.ps1`.
- [ ] Review `install_scheduled_tasks.ps1 -WhatIf`.
- [ ] Run `install_scheduled_tasks.ps1 -Install`.
- [ ] Confirm offline smoke test PASS, task `MSO-Daily-Rehearsal`, and next run.
- [ ] Keep the host on Eastern Time and logged in for the v1 task.

## Before the first formal day

- [ ] Complete a full-day rehearsal with no future timestamps or backfill.
- [ ] Confirm all core ETF Direction inputs and at least 80% constituent coverage.
- [ ] Confirm issuer membership snapshot is frozen for the run.
- [x] Confirm publication audit and Pages build pass.
- [ ] Deliberately choose to start formal Data Shadow; setup does not start it.
- [ ] Confirm Model Shadow, paper positions, and real orders remain disabled.

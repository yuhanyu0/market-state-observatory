# Operations Runbook

## Boundaries

The runtime is `DATA_CAPTURE_ONLY`. It may collect, freeze, quality-check,
derive, redact, commit public data, push, and trigger Pages. It cannot create a
paper position or real order. A missed observation remains missing.

## One-time setup

From the project root in non-elevated PowerShell:

```powershell
.\ops\windows\setup_alpaca_credentials.ps1
.\ops\windows\setup_github_auth.ps1
.\ops\windows\install_scheduled_tasks.ps1 -WhatIf
.\ops\windows\install_scheduled_tasks.ps1 -Install
```

The Alpaca command initializes the private runtime when needed, prompts for the
Key ID and a SecureString secret, exports a current-user DPAPI credential, and
prints only the path plus PRESENT status. The GitHub command never requests or
displays a token. The scheduler installation first performs an offline dry-run.

## Daily runtime

`MSO-Daily-Runtime` starts at 09:20 ET on weekdays. The Python runtime still
checks the exchange calendar, early closes, system clock skew, and single
instance lock. It captures 09:30, 10:00 settlement, 12:00, 15:30, 15:45, and the
session-close diagnostic. At open, 10:00, and 15:45 it links the corresponding
previous-observation label.

Manual rehearsal:

```powershell
.\ops\windows\run_full_day_rehearsal.ps1
```

Manual formal Data Shadow, only after setup and an accepted rehearsal:

```powershell
.\ops\windows\run_formal_data_shadow.ps1
```

No command may be run after an observation point to reconstruct that point.
A successful scheduled formal run automatically publishes the derived quality
snapshot after session close. Rehearsals, failed collection runs, and formal
runs without an immutable quality artifact do not publish.

## Health and recovery

```powershell
.\ops\windows\runtime_health_check.ps1
.\ops\windows\show_scheduled_task_status.ps1
.\ops\windows\run_scheduled_task_smoke_test.ps1
```

The daemon resumes the latest incomplete same-day run, reads immutable recovery
checkpoints, and never overwrites raw or manifest artifacts. Network errors
produce missing observations. A stale process lock is removed only when it is
older than 15 minutes and its PID is no longer running.

## Public snapshot

Manual recovery publication after session quality exists:

```powershell
.\ops\windows\publish_public_snapshot.ps1 `
  -PrivateQualityPath '<runtime>\data_shadow\YYYY-MM-DD\<run_id>\quality\DATA_QUALITY.json' `
  -Push
```

Projection, redaction, schema validation, forbidden-field scanning, manifest,
and secret audit all happen before Git. The publisher changes `public-data`
only, then dispatches the Pages workflow on `main`.

## Incident response

1. Stop the task with Task Scheduler; do not delete private evidence.
2. Run the health check and inspect only runtime logs and immutable manifests.
3. If a credential leak is suspected, disable publication, rotate at Alpaca,
   rerun credential setup, and record the incident without the value.
4. If a public audit fails, do not force push. Correct the projection or policy.
5. If clock skew exceeds five seconds, correct Windows time before collection.
6. Never repair a day by backfilling an expired observation point.

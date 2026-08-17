# Changelog

## 0.4.5 - 2026-08-17

- Put every scheduled runtime process tree in a named Windows Job Object with
  `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, using suspended child creation so Job
  assignment completes before Python executes.
- Added PID creation-time, release, task, Job, launcher, runtime, and run ownership
  evidence; operator state now separates scheduler state from verified process truth.
- Added identity-scoped `stop_runtime.ps1`, live-process and lock-aware release
  selection/start gates, and append-only abort control markers for incomplete runs.
- Preserved the interrupted 2026-08-17 v0.4.3 rehearsal without backfill or a PASS,
  and restarted the three-session soak requirement in a new v0.4.5 lane.

## 0.4.4 - 2026-08-14

- Replaced bundled REST completeness with one explicit PIT observation row per
  planned symbol, using the pre-REST WebSocket freeze as primary evidence.
- Added independent quote, trade, completed-bar, and VWAP statuses plus REST
  reconciliation that cannot replace the frozen primary state.
- Defined exact-open bar and VWAP as `NOT_YET_DEFINED`, split atomic freeze
  duration from provider event-time dispersion, and scoped Transmission quality
  to its decision snapshot.
- Added per-field readiness rates, hourly stream rotation, current-hour durable
  checkpoints and crash recovery, an independent operator heartbeat, and
  Windows PowerShell 5.1-safe operator JSON.
- Preserved the v0.4.3 Day A quality failure and required a new v0.4.4 lane with
  three new scheduler-driven PASS trading dates before Formal promotion.

## 0.4.3 - 2026-08-13

- Changed the scheduler default from formal to rehearsal and split rehearsal and
  formal into distinct task names that cannot both be active.
- Added a fail-closed Formal Data Shadow promotion artifact tied to the frozen
  release and at least three complete scheduler-driven rehearsal sessions.
- Added runtime and quality-layer defenses preventing rehearsals from entering
  the 20-day gate and preventing Formal Data Shadow from entering Model Shadow.
- Upgraded task status, registered-action smoke testing, PowerShell compatibility
  coverage, and frozen release identity for scheduler safety.

## 0.4.2 - 2026-08-13

- Fixed Windows PowerShell 5.1 process launching by replacing `ArgumentList` and
  `Environment` dependencies with a shared `ProcessStartInfo.Arguments` quoting
  helper and `EnvironmentVariables` API.
- Forced credential smoke tests and runtime launchers to use the integrity-checked
  frozen `release_python`, isolated mode, release working directory, and frozen
  wheel import path.
- Added Windows argument round-trip, credential safety, output, exit-code,
  cleanup, no-log, and dual-edition PowerShell compatibility tests.
- Extended production release identity with launcher/helper hashes, minimum
  Windows PowerShell version, tested shells, and release interpreter path class.

## 0.4.1 - 2026-08-13

- Replaced per-message WebSocket files with a bounded latest-state cache and
  immutable hourly Zstandard stream chunks.
- Added XNYS calendar-derived observation schedules, early-close handling, and
  atomic cross-section freeze/skew evidence.
- Added immutable label settlement, frozen wheel runtime identity, fail-closed
  publication locking/retry, local alerts, and a loopback operator console.
- Replaced operational UI constants with schema-validated public JSON, explicit
  stale/evidence-grade states, and insufficient-observer semantics.
- Added clean release packaging, early-close/crash/publication/schema tests, and
  a one-million-message 35-symbol stream load acceptance test.

## 0.4.0 - 2026-08-12

- Formalized 16 Draft 2020-12 schemas and readiness-state separation.
- Added typed evidence, conflict, probe, certificate, playbook, and memory objects.
- Added the complete `mso` CLI and fail-closed publication layer.
- Added eight end-to-end synthetic scenarios and public-safe Day 0B import.
- Added the independent responsive Observatory website and later upgraded it to
  a nine-route React product.
- Added observer isolation, Theme Radar role, decision sufficiency, active probe,
  Direction, Transmission, Episode, playbook, vehicle, privacy, and roadmap docs.
- Added Python 3.11/3.12 CI, Ruff, strict mypy, publication audit, link checking,
  manifest verification, and expanded tests.
- Isolated Graph SSM, field models, and semantic/event research under disabled
  labs.
- Added an external `%LOCALAPPDATA%` private runtime, current-user DPAPI
  credential flow, explicit SIP daemon, crash recovery, quality engine, and
  Windows Task Scheduler tooling.
- Rebuilt the product UI with Vite, React, and TypeScript; added Today, theme
  detail, evidence drawer, certificate, experiment, and data-quality workflows.
- Added a `public-data` publication firewall and dual-branch Pages deployment.

## 0.3.0 - 2026-08-10

- Recorded the redacted Day 0B Alpaca SIP afternoon rehearsal.
- Added initial per-theme input-readiness reporting and static experiment page.

## 0.2.0 - 2026-08-10

- Created the standalone architecture, seed schemas, package, and static site.

## 0.1.0

- Initial architecture-only prototype.

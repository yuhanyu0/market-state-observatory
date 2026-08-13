# Build Plan

## Objective

Release Market State Observatory 0.4.0 as an independent public research and
engineering project. The system turns multiple incomplete observations into an
auditable evidence state, response mode, decision-sufficient State Certificate,
stateful research playbook, shadow outcome, and reflexive memory. It never
creates broker orders.

## Core Contracts

1. Separate facts, observer inference, state interpretation, playbook decision,
   and execution evidence.
2. Implement the Direction -> Transmission -> Episode -> Playbook -> Vehicle
   chain without treating data readiness as market direction.
3. Preserve disagreement, uncertainty, invalidation, next discriminating probe,
   `DATA_BLOCKED_NO_DECISION`, `WAIT`, and `NO TRADE` states.
4. Keep Theme Radar isolated as a structural-attention observer. It cannot create
   direction, themes, labels, gates, or actions.
5. Constrain LLM use to rendering validated structured certificates; it cannot
   create observations or facts.

## Website

Build a dependency-light, white, accessible, responsive, print-friendly static
site backed only by public JSON. Cover the observatory, themes, certificates,
experiments, architecture, methodology, validation, research, roadmap, glossary,
status, and project boundary. Display research states only, never live BUY/SELL
advice.

## Python Package

Provide typed domain models, Draft 2020-12 schema validation, observer registry,
evidence graph compilation, conflict detection, next-probe recommendation,
certificate compilation, stateful playbook decisions, vehicle eligibility,
redaction, publication auditing, experiments, reflexive memory, and the `mso`
CLI. The package must not contain broker execution code.

## Public / Private Boundary

Accept only already-redacted JSON through fail-closed import bridges. Scan schema,
secrets, forbidden fields, and forbidden paths before writing only to `public/`
under `public/data/`. Never access `.env`, Credential Manager, account data, raw
provider payloads, positions, orders, Data Shadow runs, or Model Shadow runs.

## CI

Add Python 3.11/3.12 tests, Ruff, mypy, schema/example validation, publication
audit, secret/forbidden-path scanning, static-link checks, manifest verification,
Dependabot, CODEOWNERS, issue templates, pull-request template, and GitHub Pages
deployment from the Vite `dist/web/` build.

## Synthetic Demo

Create eight synthetic, non-account scenarios spanning positive/broad onset,
unresolved attention, narrow transmission, broad negative propagation,
exhaustion, retest, data blockage, and observer conflict. Demonstrate the full
Observation-to-Certificate pipeline while restricting outcomes to `WAIT` or
`MODEL_SHADOW_ONLY` and keeping all order flags false.

## Integration Bridge

Define public Alpaca rehearsal-summary and Theme Radar observer contracts. The
Alpaca bridge imports redacted summaries only. The Theme Radar bridge transports
structural attention, persistence/migration interpretation, provenance, and
uncertainty only.

## Experimental Modules

Place Graph SSM, PDE/field approaches, semantic/event observers, and other
unvalidated complexity under `labs/` or disabled feature flags. They cannot alter
the stable contracts or default pipeline.

## Publication Steps

1. Validate every schema and example.
2. Run tests, Ruff, mypy, repository validation, publication audit, link checks,
   secret scans, and the synthetic demo.
3. Build and verify public manifests and hashes.
4. Recheck the old repository's HEAD/status exactly.
5. Inspect GitHub CLI version/auth/help and confirm the target repository does
   not already exist.
6. Only after every gate passes, initialize an independent `main` repository,
   create focused commits, create the public GitHub repository, and push.
7. Deploy Pages through Actions and claim success only after workflow and HTTP
   verification.

## Pruning Boundary

The stable schemas, public/private boundary, typed evidence pipeline, baseline
playbooks, synthetic reference corpus, and publication audit are core. Labs,
advanced observers, speculative response operators, optional visualizations, and
research notes are explicitly removable if they do not demonstrate same-date
incremental value.

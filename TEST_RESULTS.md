# Test Results

Validated locally on 2026-08-14 ET with the v0.4.4 source tree.

| Gate | Result |
|---|---|
| Python unit/contract/security | PASS, 105 tests |
| Ruff | PASS |
| strict mypy | PASS, 52 source files |
| JSON Schema Draft 2020-12 | PASS, 25 schemas |
| validated public/example objects | PASS, 101 objects |
| Vitest + React Testing Library | PASS, 4 tests |
| Playwright desktop/mobile | PASS, 12 tests |
| React production build | PASS |
| route/asset/public JSON check | PASS, 9 routes |
| publication audit | PASS |
| credential/secret scan | PASS |
| Windows PowerShell | PASS, Desktop 5.1.26100.9168 |
| PowerShell Core | PASS, 7.6.4 |
| process compatibility and scheduler safety | PASS in both editions |
| 35-symbol stream load | PASS, 1,000,000/1,000,000 reconstructed |
| stream loss / duplicate / drop | PASS, 0 / 0 / 0 |
| stream file bound | PASS, 8 chunks + 8 manifests |
| crash durability | PASS, finalized hour hash unchanged |
| v0.4.4 scheduler install | NOT RUN by design |
| Formal Data Shadow | NO-GO, 0 new PASS dates |
| paper positions / real orders | 0 / 0 |

The immutable v0.4.3 Day A failure was audited offline and was not reclassified.
The v0.4.4 release must complete three new scheduler-driven PASS trading dates.

# Test Results

Validated locally on 2026-08-13 ET with Python 3.13, Node 22, Vite 6, and
Playwright Chromium 151.

| Gate | Result |
|---|---|
| Python unit/contract/security | PASS, 64 tests |
| Ruff | PASS |
| strict mypy | PASS, 43 source files |
| JSON Schema Draft 2020-12 | PASS, 17 schemas |
| validated example objects | PASS, 87 objects |
| Vitest + React Testing Library | PASS, 3 tests |
| Playwright desktop/mobile | PASS, 12 tests |
| axe serious/critical | PASS, zero on Today desktop/mobile |
| React production build | PASS |
| initial JavaScript | 182.27 kB raw, 56.98 kB gzip |
| route/asset/public JSON check | PASS, 9 routes |
| publication audit | PASS |
| credential/secret scan | PASS |
| PowerShell parser | PASS, 21 scripts |
| unattended runtime dry-run | PASS, no network call |
| synthetic scenarios | PASS, 8 scenarios, zero orders |

Public-safe screenshots:

- `docs/screenshots/today-desktop.png`
- `docs/screenshots/today-mobile.png`
- `docs/screenshots/theme-detail-desktop.png`

The host integration gates remain intentionally unrun: no DPAPI credential was
created, no live SIP request was made from this project, no scheduled task was
installed, and no formal Data Shadow run was created.

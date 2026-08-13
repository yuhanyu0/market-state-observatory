# Current State Audit

Audit date: 2026-08-13 ET.

## Local and source state

- Project: `C:\Users\Chinajushiusa\Documents\Codex\market-state-observatory`.
- Seed ZIP was fully extracted and its provenance hash is recorded in
  `SEED_PROVENANCE.md`.
- At the start of this hardening pass the new directory had no `.git` metadata.
- GitHub CLI 2.97.0 is installed and authenticated as `yuhanyu0` through the
  system keyring. The target repository was verified as absent before any
  creation or push; no existing repository can be overwritten by this setup.
- The old Theme Radar worktree baseline remains separately recorded in
  `OLD_REPOSITORY_READONLY_BASELINE.md` and was treated read-only.

## Test and product state at audit start

- Python suite: 47 passed and one README wording assertion failed. The wording
  was corrected before hardening continued.
- Website: generated dependency-free HTML in `site/`, with static JSON duplicated
  between `site/data` and public paths.
- Publication checks existed but permitted more than one public destination.
- No external runtime path resolver, DPAPI credential flow, Windows scheduler,
  unattended daemon, or public-data worktree publisher existed.

## Public/private and credential audit

- No Alpaca credential value, token, account number, order, position, raw quote,
  trade, bar, or provider response was found in the new project.
- `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` were absent from the collector
  process environment during this audit; their values were never requested.
- `%LOCALAPPDATA%\MarketStateObservatoryRuntime` was not initialized.
- The DPAPI file `secrets\alpaca.credential.xml` did not exist.
- Formal Data Shadow and Model Shadow were not started; paper positions and real
  orders were zero.

## Hardening disposition

This pass replaces the duplicated public path with `public/data`, keeps all real
runtime state outside Git, and adds a React product build. The legacy `site/`
tree is ignored and is no longer a release input.

## Hardening outcome

- The new public repository is
  `https://github.com/yuhanyu0/market-state-observatory`.
- `main` contains product source; `public-data` contains redacted data only.
- GitHub Pages is deployed from Actions at
  `https://yuhanyu0.github.io/market-state-observatory/`.
- GitHub authentication uses the system keyring. Alpaca DPAPI credentials,
  private runtime initialization, and Task Scheduler installation remain
  deliberately incomplete.

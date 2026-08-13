# Migration Notes 0.4.0

- The product build moved from generated `site/` HTML to `web/` and `dist/web/`.
- Generated public JSON now belongs only under `public/data/`.
- Real runtime data moved permanently outside Git to LocalAppData.
- `main` is product source; `public-data` is generated redacted data.
- Existing v0.3 public examples remain evidence references and are not formal
  Data Shadow observations.

Run `scripts/setup.ps1`, then the three one-time Windows operations in
`FIRST_RUN_CHECKLIST.md`. Do not copy old private run directories into this
repository.

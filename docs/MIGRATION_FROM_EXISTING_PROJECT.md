# Migration from the existing local project

This repository must be created in a new directory and new GitHub repository. The source project is read-only during migration.

Safe candidates for later migration:

- public schema and methodology documents;
- provider adapter interfaces;
- redacted status builders;
- generic tests;
- public-safe aggregate validation summaries.

Never copy automatically:

- `logs/` or `assets/` from Theme Radar Log;
- API keys or environment files;
- raw Alpaca payloads;
- broker account data;
- positions or orders;
- private Data Shadow runs.

Use `scripts/import_from_existing_project.py --dry-run` first.

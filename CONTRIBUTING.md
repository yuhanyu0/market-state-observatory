# Contributing

## Principles

1. Preserve point-in-time lineage.
2. Separate facts, inference and action.
3. Keep observer disagreement visible.
4. Add complexity only when it shows incremental out-of-sample value.
5. Never publish secrets, private provider payloads or order-capable information.

## Pull requests

Every PR should state:

- which canonical object or observer it changes;
- what evidence grade it affects;
- whether it changes a public schema;
- what negative controls or tests were added;
- whether the website output changes.

Use conventional commit prefixes where possible: `docs:`, `schema:`, `site:`, `observer:`, `validation:`, `security:`.

# Schema versioning

- Patch: documentation or optional-field clarification.
- Minor: backward-compatible optional fields or new enum values with safe defaults.
- Major: required-field, semantic or evidence-grade changes.

Every public payload carries a schema version. A major schema change requires:

- an ADR;
- migration notes;
- updated examples;
- updated website renderer;
- compatibility tests.

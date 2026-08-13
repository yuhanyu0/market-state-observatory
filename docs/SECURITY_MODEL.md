# Security model

## Threats

- credential leakage through logs, exceptions, public JSON or screenshots;
- accidental publication of licensed raw market-data payloads;
- post-hoc reconstruction presented as point-in-time evidence;
- an analysis path silently creating an order-capable path;
- LLM-generated facts or catalysts entering a State Certificate;
- schema drift allowing live-eligible labels without required evidence.

## Controls

- separate public and private directories;
- append-only raw evidence outside the public repository;
- public-tree secret audit in CI;
- `real_order_created=false` in public playbook schemas;
- point-in-time timestamp invariants;
- explicit evidence grades;
- code review for schema and gate changes;
- fail-closed publication.

## Residual risk

Static checks cannot prove that a provider license permits redistribution or that all semantic event data has complete known-at provenance. Those questions require provider-specific legal and data-governance review.

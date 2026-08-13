# Release Strategy

- `main`: stable product code, schemas, docs, and fallback public samples.
- `public-data`: generated redacted JSON only.
- `feature/*`: product changes through review.
- `research/*`: disabled experimental modules.

Semantic versions cover product and evidence contracts. Each release runs
Python tests, Vitest, Playwright, Ruff, mypy, schema validation, secret scan,
publication audit, React build, link checks, and manifest verification.

Daily public-data publication never modifies `main`. Pages always builds code
from `main`, overlays audited data from `public-data`, then deploys the static
artifact. Rollback means redeploying a prior `main` release and/or reverting a
public-data commit, without touching the private runtime.

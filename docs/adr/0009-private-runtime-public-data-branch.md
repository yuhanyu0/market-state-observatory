# ADR 0009: External Runtime and Public-Data Branch

## Status

Accepted.

## Decision

Secrets and operating data live under the current user's LocalAppData runtime,
never below the Git repository. Product code lives on `main`; generated,
redacted JSON lives on `public-data`. Pages checks out `main`, overlays the data
branch, validates the publication boundary, builds React, and deploys.

## Consequences

Daily publication cannot churn product history. A compromised public artifact
cannot reveal a raw provider path because projection, policy, schema, scan, and
manifest checks all precede Git. Local backup and retention are operational
responsibilities outside this public repository.

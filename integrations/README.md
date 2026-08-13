# Public Integration Bridges

Integrations are publication boundaries, not runtime dependencies. They accept
already-redacted JSON, validate the appropriate schema, scan secret and forbidden
fields, and fail closed before writing only to `public/data/`.

No bridge reads environment files, Credential Manager, broker accounts, raw
provider responses, positions, orders, private Data Shadow runs, or private Model
Shadow runs. Market State Observatory runs independently of the source systems.

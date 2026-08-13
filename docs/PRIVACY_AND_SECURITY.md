# Privacy and Security

The public repository contains contracts, synthetic examples, public-safe
summaries, and static site data. It must not contain credentials, account
identifiers, raw provider responses, private Data Shadow or Model Shadow runs,
positions, orders, broker directories, or credential exports.

Imports accept already-redacted JSON only. They validate schema, scan secret and
forbidden-field patterns, reject unsafe payloads, and write only below
`public/data/`. Failure is closed: no partial public file remains.

Environment files and private directories are ignored. CI reports only pass/fail
findings and never prints environment values. The package has no order-capable
adapter. Security incidents should be reported through `SECURITY.md`, not a
public issue containing sensitive evidence.

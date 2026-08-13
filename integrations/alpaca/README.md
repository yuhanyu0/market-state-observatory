# Alpaca Public Summary Bridge

This bridge accepts a redacted rehearsal or data-quality summary. It is not an
Alpaca market-data adapter and has no authentication or order capability.

Allowed content includes provider/feed labels, aggregate capture counts,
timestamp-quality counts, quote-age summaries, readiness counts, non-sensitive
collector hashes, and explicit zero/false order and position fields. Raw provider
responses and account fields are rejected.

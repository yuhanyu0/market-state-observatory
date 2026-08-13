# Security policy

## Report privately

Do not open a public issue for:

- credential exposure;
- provider payloads containing account data;
- a path that can create or route a real order;
- publication of private raw market-data archives;
- timestamp or backfill bypasses.

## Hard guarantees expected from this repository

- environment-variable values are never rendered to the public site;
- public artifacts are scanned for common credential names and token patterns;
- missed scheduled observations remain missing;
- `event_time_utc <= observed_at_utc` and `data_max_timestamp <= observed_at_utc`;
- the public site contains no positions or orders.

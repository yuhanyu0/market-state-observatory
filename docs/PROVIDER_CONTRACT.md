# Provider contract

A provider adapter must expose sanitized request metadata, immutable raw-response hashes and event/observation timestamps without persisting credentials.

Minimum record envelope:

- collector request ID;
- optional provider request ID;
- request start and observation time;
- event time and maximum embedded timestamp;
- explicit feed / venue scope;
- raw-response SHA256;
- parser and ingestion version;
- backfill flag.

A provider's successful HTTP response does not by itself establish real-time entitlement, completeness, NBBO coverage or redistribution rights. Those properties must be recorded separately.

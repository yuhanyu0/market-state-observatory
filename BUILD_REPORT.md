# Build Report

## Result

Market State Observatory 0.4.0 is implemented as a data-only private runtime,
fail-closed public publication system, and static React product.

The production build generated `dist/web/index.html`, 19.49 kB CSS, 40.49 kB
application JavaScript, and 141.78 kB React vendor JavaScript. Total JavaScript
is below the 220 kB initial budget.

## Runtime

The Alpaca adapter uses explicit SIP REST and `wss://stream.data.alpaca.markets/v2/sip`,
immutable raw responses, collector UUIDs, provider request IDs when available,
timestamp checks, no backfill, point-in-time VWAP, constituent coverage, and
layered readiness. Windows automation provides DPAPI credential storage,
Task Scheduler, recovery, health alerts, and data-only modes.

## Product

The nine-route interface is responsive, keyboard accessible, reduced-motion
aware, and print friendly. Today exposes operational health without requiring a
methodology read. Theme cards never confuse data readiness with signed state.

## Boundary

Formal Data Shadow and Model Shadow are not started. No paper position or real
order exists. GitHub authentication uses the system keyring, `main` and the
redacted `public-data` branch are pushed, and the Pages deployment is live.

# Product Handoff

## Product

The React observatory opens on Today and exposes ET/UTC time, freshness, runtime
phase, 0/20 Data Shadow gate, timeline, six themes, data gaps, health, and the
evidence boundary. Theme detail, evidence drawer, printable certificates,
experiments, data quality, methodology, research, and status are hash-routed for
static Pages hosting.

The deployed product is available at
https://yuhanyu0.github.io/market-state-observatory/.

Theme cards explicitly separate `DATA_READY`, `MODEL_ESTIMATED`, and
`DECISION_ELIGIBLE`. The application never translates input readiness into a
positive Direction state and shows no BUY/SELL output.

## UX and verification

- Responsive white/black/gray design system with text-backed state colors.
- Keyboard navigation, skip link, Escape-close drawer, reduced motion, print CSS.
- Global theme/range/state filters, ET/UTC toggle, JSON/CSV download, permalinks.
- Graceful loading, failure, empty, and data-blocked states.
- Chromium desktop/mobile screenshots in `docs/screenshots/`.

Product requirements, journeys, information architecture, accessibility, error
states, publication UX, analytics policy, and release strategy live in
`docs/product/`.

## Evidence state

The visible fallback data is the public-safe Day 0B partial rehearsal. It is not
today's live state, does not count toward the gate, and does not authorize a
model or position. Daily public-data publication will replace status and append
aggregate quality snapshots only after setup.

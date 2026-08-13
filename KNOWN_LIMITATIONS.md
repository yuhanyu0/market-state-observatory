# Known Limitations

- The host has not completed DPAPI credential setup or a full-day rehearsal.
- GitHub repository, `public-data`, and Pages are active, but daily publication
  cannot run until DPAPI credential setup and Task Scheduler installation.
- Task Scheduler v1 requires the user to be logged on and Windows set to Eastern
  Time; Python independently handles DST through `America/New_York`.
- The exchange calendar covers standard NYSE holidays and common early closes,
  not unscheduled exchange closures. Provider clock diagnostics remain required.
- Issuer membership is frozen from the configured runtime universe; issuer-
  specific live membership and announcement-known-at corporate-event adapters
  remain backlog items.
- Session close is a provider diagnostic, not a claim of official auction
  entitlement.
- Automated accessibility checks do not replace manual screen-reader review.
- Public SIP redistribution rights remain conservative: only derived aggregate
  state is published.
- Graph SSM, Episode, playbooks, vehicle overlay, and Model Shadow are disabled.

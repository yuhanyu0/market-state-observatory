# Direction

Direction estimates the signed release of a theme relative to the market. It is
separate from attention, absolute movement, volatility, and data readiness.

The transparent baseline begins with point-in-time relative return, constituent
breadth and median relative return, ETF position within VWAP/range, and
close-period confirmation. It preserves raw components and uncertainty. Outputs
are `positive`, `negative`, or `unresolved`.

Historical reconstruction cannot claim a same-day executable close signal when
features are computed after that close. Prospective estimates must retain event,
observation, and maximum-data timestamps. Direction survives only if it provides
out-of-sample signed information beyond simple momentum on the same dates.

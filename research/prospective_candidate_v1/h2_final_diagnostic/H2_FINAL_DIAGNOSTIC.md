# Final H2 Diagnostic

Evidence lane: `H2_HISTORICAL_RECONSTRUCTED_DAILY`. D1 is used only as a frozen zero-threshold veto on a 5-day relative-momentum ranking; it is not traded as a standalone signal.

Panel: 18703 theme-date rows, 3654 dates, 6 themes. Raw/unadjusted ETF data only; no constituent lookback.

| Horizon | Dates | Mean 10 bps/leg spread | Median | Bootstrap 95% CI |
|---|---:|---:|---:|---:|
| next_open_to_3d_close | 3486 | -8.60 bps | +0.00 bps | [-18.79, +1.99] bps |
| next_open_to_5d_close | 3486 | -13.48 bps | +0.00 bps | [-28.00, +0.36] bps |

Conclusion: No clear robust after-cost cross-theme result. H2 model mining is closed.

`H2_MODEL_MINING_CLOSED=true`; `decision_eligible=false`; `paper_positions=0`; `real_orders=0`.

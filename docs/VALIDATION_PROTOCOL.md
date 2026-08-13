# Validation protocol

## Sequential ablation

```text
D              = Direction only
D + T          = + Transmission
D + T + E      = + Episode
D + T + E + P  = + Playbook
```

All arms use the same dates, themes, decision cutoffs, execution assumptions and cost model.

## Requirements

- chronological nested walk-forward;
- purge and embargo for overlapping horizons;
- episode- or block-clustered uncertainty;
- no random date split;
- thresholds selected on training windows only;
- untouched test-window scoring;
- costs and quoted spread included;
- theme and regime strata;
- top-day and top-theme concentration diagnostics;
- explicit no-trade coverage.

A layer that does not improve calibration, net utility, tail risk or false-positive control is removed or downgraded.

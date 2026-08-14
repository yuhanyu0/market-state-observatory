# Day A Capture Forensic Report

Source run: `2026-08-14-bc1d37197bc0`. This was an offline, immutable audit. 
No Alpaca call was made, no Day A artifact was altered, and Day A remains `FAIL`.

## Point Summary

| Point | REST rows | WebSocket | Missing primary causes |
|---|---:|---:|---|
| decision_snapshot | 24/35 | 35/35 | quote_future_vs_collector_clock=11 |
| midpoint_snapshot | 30/35 | 35/35 | quote_future_vs_collector_clock=5 |
| next_10_00 | 25/35 | 35/35 | quote_future_vs_collector_clock=10 |
| open_snapshot | 0/35 | 35/35 | no_eligible_completed_bar=35 |
| preclose_snapshot | 29/35 | 35/35 | quote_future_vs_collector_clock=6 |
| session_close_diagnostic | 30/35 | 35/35 | quote_future_vs_collector_clock=5 |

## Missing Symbols

| Point | Symbol | Primary reason | All reasons | Quote age (s) | Bars |
|---|---|---|---|---:|---:|
| decision_snapshot | AMD | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.066952 | 375 |
| decision_snapshot | CIBR | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.160786 | 361 |
| decision_snapshot | CRM | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.107127 | 375 |
| decision_snapshot | CSCO | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.167517 | 375 |
| decision_snapshot | MSFT | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.022991 | 375 |
| decision_snapshot | NVDA | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.123638 | 375 |
| decision_snapshot | PL | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.058522 | 375 |
| decision_snapshot | RKLB | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.058023 | 375 |
| decision_snapshot | SMH | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.170342 | 375 |
| decision_snapshot | SOXX | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.082807 | 375 |
| decision_snapshot | SPY | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.156153 | 375 |
| midpoint_snapshot | CIBR | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.046328 | 191 |
| midpoint_snapshot | NVDA | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.049868 | 195 |
| midpoint_snapshot | SMH | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.089894 | 195 |
| midpoint_snapshot | SPY | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.049677 | 195 |
| midpoint_snapshot | URA | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.041502 | 192 |
| next_10_00 | AMD | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.019625 | 30 |
| next_10_00 | ARKX | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.008717 | 27 |
| next_10_00 | AVGO | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.003890 | 30 |
| next_10_00 | CSCO | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.062975 | 30 |
| next_10_00 | NVDA | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.061332 | 30 |
| next_10_00 | PL | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.008308 | 30 |
| next_10_00 | RKLB | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.028120 | 30 |
| next_10_00 | SMH | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.052392 | 30 |
| next_10_00 | SPY | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.062782 | 30 |
| next_10_00 | TSM | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.032429 | 30 |
| open_snapshot | AMD | no_eligible_completed_bar | no_eligible_completed_bar | 0.146890 | 0 |
| open_snapshot | ARKX | no_eligible_completed_bar | no_eligible_completed_bar | 0.122286 | 0 |
| open_snapshot | ASTS | no_eligible_completed_bar | no_eligible_completed_bar | 0.166695 | 0 |
| open_snapshot | AVGO | no_eligible_completed_bar | no_eligible_completed_bar | 0.116799 | 0 |
| open_snapshot | CCJ | no_eligible_completed_bar | no_eligible_completed_bar | 0.239060 | 0 |
| open_snapshot | CIBR | no_eligible_completed_bar | no_eligible_completed_bar | 0.267706 | 0 |
| open_snapshot | CLOU | no_eligible_completed_bar | no_eligible_completed_bar | 0.331699 | 0 |
| open_snapshot | CRM | no_eligible_completed_bar | no_eligible_completed_bar | 0.143236 | 0 |
| open_snapshot | CRWD | no_eligible_completed_bar | no_eligible_completed_bar | 0.490175 | 0 |
| open_snapshot | CSCO | no_eligible_completed_bar | no_eligible_completed_bar | 0.107917 | 0 |
| open_snapshot | ENPH | no_eligible_completed_bar | no_eligible_completed_bar | 0.429643 | 0 |
| open_snapshot | FSLR | no_eligible_completed_bar | no_eligible_completed_bar | 0.185319 | 0 |
| open_snapshot | FTNT | no_eligible_completed_bar | no_eligible_completed_bar | 0.279182 | 0 |
| open_snapshot | HACK | no_eligible_completed_bar | no_eligible_completed_bar | 1.364163 | 0 |
| open_snapshot | ICLN | no_eligible_completed_bar | no_eligible_completed_bar | 0.507985 | 0 |
| open_snapshot | IRDM | no_eligible_completed_bar | no_eligible_completed_bar | 0.398442 | 0 |
| open_snapshot | MSFT | no_eligible_completed_bar | no_eligible_completed_bar | 0.123395 | 0 |
| open_snapshot | NLR | no_eligible_completed_bar | no_eligible_completed_bar | 0.272372 | 0 |
| open_snapshot | NOW | no_eligible_completed_bar | no_eligible_completed_bar | 0.231018 | 0 |
| open_snapshot | NVDA | no_eligible_completed_bar | no_eligible_completed_bar | 0.127066 | 0 |
| open_snapshot | OKLO | no_eligible_completed_bar | no_eligible_completed_bar | 0.426060 | 0 |
| open_snapshot | ORCL | no_eligible_completed_bar | no_eligible_completed_bar | 0.120242 | 0 |
| open_snapshot | PANW | no_eligible_completed_bar | no_eligible_completed_bar | 0.366834 | 0 |
| open_snapshot | PL | no_eligible_completed_bar | no_eligible_completed_bar | 0.816940 | 0 |
| open_snapshot | RKLB | no_eligible_completed_bar | no_eligible_completed_bar | 0.126268 | 0 |
| open_snapshot | RUN | no_eligible_completed_bar | no_eligible_completed_bar | 0.110478 | 0 |
| open_snapshot | SKYY | no_eligible_completed_bar | no_eligible_completed_bar | 0.410769 | 0 |
| open_snapshot | SMH | no_eligible_completed_bar | no_eligible_completed_bar | 0.107853 | 0 |
| open_snapshot | SOXX | no_eligible_completed_bar | no_eligible_completed_bar | 0.110525 | 0 |
| open_snapshot | SPY | no_eligible_completed_bar | no_eligible_completed_bar | 0.118380 | 0 |
| open_snapshot | TAN | no_eligible_completed_bar | no_eligible_completed_bar | 2.492459 | 0 |
| open_snapshot | TSM | no_eligible_completed_bar | no_eligible_completed_bar | 0.169368 | 0 |
| open_snapshot | UEC | no_eligible_completed_bar | no_eligible_completed_bar | 2.460779 | 0 |
| open_snapshot | UFO | no_eligible_completed_bar | no_eligible_completed_bar | 0.513194 | 0 |
| open_snapshot | URA | no_eligible_completed_bar | no_eligible_completed_bar | 0.186730 | 0 |
| preclose_snapshot | ASTS | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.077280 | 360 |
| preclose_snapshot | AVGO | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.080916 | 360 |
| preclose_snapshot | NLR | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.048936 | 244 |
| preclose_snapshot | OKLO | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.181977 | 360 |
| preclose_snapshot | SMH | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.185144 | 360 |
| preclose_snapshot | SOXX | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.179300 | 360 |
| session_close_diagnostic | CRM | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.244960 | 389 |
| session_close_diagnostic | MSFT | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.007559 | 389 |
| session_close_diagnostic | NVDA | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.040715 | 389 |
| session_close_diagnostic | SPY | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.242049 | 390 |
| session_close_diagnostic | UFO | quote_future_vs_collector_clock | quote_future_vs_collector_clock | -0.177320 | 225 |

## Active-Symbol Hypothesis

For SPY, NVDA, SMH, and SOXX, provider absence is distinguished from the old timestamp/bar eligibility checks in the rows above.

`all_exclusions_due_to_timestamp_or_bar_eligibility = true`

## Interpretation Boundary

These classifications reproduce the v0.4.3 exclusion order. They do not apply v0.4.4 semantics retroactively and do not change Day A quality or promotion status.

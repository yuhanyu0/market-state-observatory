# Historical Validation Report

Branch: `research/v0.5.0-historical-validation-lab`  
Frozen parent: `b91308d70d318567697dd4019648d47dc81c61de`  
Status: `retrospective_unvalidated=true`, `decision_eligible=false`, `paper_positions=0`, `real_orders=0`.

## Executive verdict

This lab does not authorize Formal Data Shadow, Model Shadow, paper positions, or orders. It validates only what the existing evidence can legally support. H2 supports an out-of-sample ETF-level Direction comparison; it does not contain historical point-in-time holdings, so Transmission and breadth-dependent Playbook claims remain untestable. Theme Radar remains an unsigned H3 attention observer.

## 1. Evidence lanes and sample size

| Evidence lane | Records | Dates / runs | Accuracy eligible | Interpretation |
|---|---:|---:|---|---|
| H1_EXACT_PIT | 18 theme-run records | 3 rehearsal runs | No: 0 settled labeled outcomes | Exact provenance, rehearsal only |
| H2_HISTORICAL_RECONSTRUCTED_DAILY | 18703 theme-date OOS records | 3654 dates | Yes, retrospective only | Raw/unadjusted daily, t close as-of, no same-day close execution claim |
| H3_THEME_RADAR_ATTENTION | 253 snapshots; 120 imported daily attention rows (119 labeled); 11 episodes | 172 snapshot dates | Attention description only | Unsigned; cannot set Direction |
| SYNTHETIC | 8 fixtures | correctness corpus | No | Correctness only |

The 120 H3 daily rows contain 113 same-day-pre-entry records and 7 shifted records. Shifted records are not promoted to same-day evidence.

## 2. Frozen horizons

| Horizon | Legal label records | Unique signal dates | Executable H2 claim |
|---|---:|---:|---|
| close_to_next_open | 18703 | 3654 | No; directional label diagnostic only |
| next_open_to_next_close | 18703 | 3654 | t+1 open entry supported |
| close_to_next_close | 18703 | 3654 | No; directional label diagnostic only |
| close_to_3d_close | 18703 | 3654 | No; directional label diagnostic only |
| close_to_5d_close | 18703 | 3654 | No; directional label diagnostic only |

All labels end after the close-t as-of. Close-origin labels are useful for direction/return-path testing but are not evidence that a post-close H2 calculation could trade the same close.

## 3. D0 / D1 / D2 primary result

Primary executable historical lane: raw/unadjusted H2, `t close information -> t+1 open entry -> t+1 close exit`, 10 bps.
D1 uses the frozen historical transparent rule `expected_relative_return > 0`; it is not a full-sample threshold choice. The separately listed historical transparent baseline is an exact alias used as a reproducibility check.

| Arm | OOS dates | Coverage | Mean net (bps) | Median net (bps) | Time-block 95% CI (bps) | Disposition |
|---|---:|---:|---:|---:|---:|---|
| D0_SIMPLE_RELATIVE | 3024 | 75.3% | -12.88 | +0.00 | [-17.41, -7.29] | DROP |
| D1_DAILY_RECONSTRUCTED | 3024 | 48.4% | -4.57 | +0.00 | [-8.23, -0.81] | DROP |
| D2_PROBABILISTIC_CANDIDATE | 3024 | 1.0% | -0.18 | +0.00 | [-0.53, +0.15] | DROP |

D0 vs D1 paired increment: +8.31 bps on 3024 common dates; bootstrap CI [+3.05, +13.17] bps.

D2 is judged on both return and probability calibration. A positive average return does not override a Brier/log-loss failure versus the expanding-window base-rate null.
D2 Brier is 0.25243296102632; the expanding base-rate Brier is 0.2499282923722555. D2 also covers under 1% of portfolio dates after its train-only gate, so it is not a usable calibrated arm.

## 4. D1 versus simple momentum

| Comparison | Common dates | Paired mean (bps) | Paired median (bps) | Bootstrap 95% CI (bps) | Status |
|---|---:|---:|---:|---:|---|
| D1_vs_5d_relative_momentum | 3024 | +12.62 | +0.00 | [+7.45, +17.97] | COMPLETE_COMMON_SAMPLE |
| D1_vs_20d_relative_momentum | 3024 | +11.50 | +0.00 | [+6.15, +17.15] | COMPLETE_COMMON_SAMPLE |
| D1_vs_D1_plus_T | 0 | NA | NA | [NA, NA] | INSUFFICIENT_EVIDENCE |

A D1 recommendation cannot be `KEEP` unless its incremental evidence, median, concentration, best-episode removal, and cost sensitivity all survive together.
Here D1's paired increment is loss avoidance against two still-worse momentum controls, not alpha: D1 itself earns -4.57 bps after 10 bps and its time-block interval is below zero.

## 5. Transmission increment

`INSUFFICIENT_EVIDENCE`. H2 has no historical point-in-time holdings. The old frozen current constituent lists were not projected backward. H1 has exact membership but no quality-pass settled outcomes. Therefore D1 vs D1+T has zero common legal dates.

## 6. Episode increment

The imported 11 Theme Radar episodes are H3 attention episodes. Their hold-until-change 10 bps mean is +105.09 bps and median is +5.41 bps, but they do not validate E0/E1 as source-native signed episode models. E1 remains `INSUFFICIENT_EVIDENCE`.
The H3 episode mean is right-tail dependent: Software_Cloud episode 7 contributed +2,313.81 bps, Semis episode 8 contributed -2,031.58 bps, and removing the best episode changes the mean to -140.32 bps. This is descriptive concentration, not Episode-model increment.

## 7. Theme Radar attention increment

The unsigned attention sample has a descriptive 10 bps mean of +10.47 bps and median of +5.29 bps. It cannot determine sign, select a source-native theme, or replace missing Transmission. The preregistered D1+T attention ablation therefore has zero legal common dates.

## 8. Playbook increment

`INSUFFICIENT_EVIDENCE`. The T+E base arm cannot be formed legally, so T+E vs T+E+Playbook cannot be evaluated. The historical `NoScript` outcomes are descriptions, not a validated Playbook win.

## 9. Cost sensitivity

| Arm | Cost (bps) | Mean net (bps) | Median net (bps) | Coverage | Max drawdown |
|---|---:|---:|---:|---:|---:|
| D0_SIMPLE_RELATIVE | 0 | -5.35 | +0.00 | 75.3% | -90.1% |
| D0_SIMPLE_RELATIVE | 5 | -9.12 | +0.00 | 75.3% | -96.5% |
| D0_SIMPLE_RELATIVE | 10 | -12.88 | +0.00 | 75.3% | -98.8% |
| D0_SIMPLE_RELATIVE | 15 | -16.64 | +0.00 | 75.3% | -99.6% |
| D0_SIMPLE_RELATIVE | 25 | -24.17 | +0.00 | 75.3% | -100.0% |
| D0_SIMPLE_RELATIVE | 50 | -42.98 | -2.17 | 75.3% | -100.0% |
| D1_DAILY_RECONSTRUCTED | 0 | +0.27 | +0.00 | 48.4% | -52.3% |
| D1_DAILY_RECONSTRUCTED | 5 | -2.15 | +0.00 | 48.4% | -69.6% |
| D1_DAILY_RECONSTRUCTED | 10 | -4.57 | +0.00 | 48.4% | -82.7% |
| D1_DAILY_RECONSTRUCTED | 15 | -6.98 | +0.00 | 48.4% | -91.1% |
| D1_DAILY_RECONSTRUCTED | 25 | -11.82 | +0.00 | 48.4% | -97.9% |
| D1_DAILY_RECONSTRUCTED | 50 | -23.92 | +0.00 | 48.4% | -99.9% |
| D2_PROBABILISTIC_CANDIDATE | 0 | -0.08 | +0.00 | 1.0% | -10.3% |
| D2_PROBABILISTIC_CANDIDATE | 5 | -0.13 | +0.00 | 1.0% | -11.3% |
| D2_PROBABILISTIC_CANDIDATE | 10 | -0.18 | +0.00 | 1.0% | -12.4% |
| D2_PROBABILISTIC_CANDIDATE | 15 | -0.23 | +0.00 | 1.0% | -13.5% |
| D2_PROBABILISTIC_CANDIDATE | 25 | -0.32 | +0.00 | 1.0% | -15.5% |
| D2_PROBABILISTIC_CANDIDATE | 50 | -0.56 | +0.00 | 1.0% | -20.7% |

## 10. Theme, month, and episode concentration

The 10 bps primary rows report top-theme absolute/positive PnL shares, top-five-date share, leave-one-theme-out, leave-one-month-out, and clustered bootstraps. Concentration is a veto: positive mean alone is not validation.

| Arm | Top theme abs PnL | Top month abs PnL | Top episode abs PnL | Top 5 dates abs PnL |
|---|---:|---:|---:|---:|
| D0_SIMPLE_RELATIVE | 33.3% | 1.6% | 1.6% | 1.5% |
| D1_DAILY_RECONSTRUCTED | 87.5% | 3.1% | 4.3% | 2.9% |
| D2_PROBABILISTIC_CANDIDATE | 76.3% | 48.2% | 24.9% | 42.3% |

Theme breakdown rows: `87`. Episode breakdown rows: `11`. Month and failure slices are in `FAILURE_SLICES.csv`.

## 11. Removing the best episodes

| Arm | Original mean (bps) | Remove best 1 | Remove best 3 | Remove best 5 |
|---|---:|---:|---:|---:|
| D0_SIMPLE_RELATIVE | -12.88 | -13.53 | -14.65 | -15.68 |
| D1_DAILY_RECONSTRUCTED | -4.57 | -5.10 | -6.08 | -6.86 |
| D2_PROBABILISTIC_CANDIDATE | -0.18 | -0.25 | -0.37 | -0.44 |

## 12. KEEP / REWRITE / DROP table

| Model / observer | Disposition |
|---|---|
| CONSTITUENT_BREADTH_ONLY | INSUFFICIENT_EVIDENCE |
| D0_SIMPLE_RELATIVE | DROP |
| D1_DAILY_RECONSTRUCTED | DROP |
| D1_PIT_FULL | INSUFFICIENT_EVIDENCE |
| D1_T_E_PLAYBOOK | INSUFFICIENT_EVIDENCE |
| D2_PROBABILISTIC_CANDIDATE | DROP |
| E0_INTERPRETABLE | DESCRIPTIVE_ONLY |
| E1_BOCPD | INSUFFICIENT_EVIDENCE |
| HISTORICAL_TRANSPARENT_BASELINE | DROP |
| SPY | DESCRIPTIVE_ONLY |
| SPY_RELATIVE_MOMENTUM_20D | DESCRIPTIVE_ONLY |
| SPY_RELATIVE_MOMENTUM_5D | DESCRIPTIVE_ONLY |
| SYNTHETIC_CORRECTNESS_CORPUS | DESCRIPTIVE_ONLY |
| T0_DAILY_LIMITED | INSUFFICIENT_EVIDENCE |
| T0_PIT_TRANSMISSION | INSUFFICIENT_EVIDENCE |
| THEME_ETF_1D_MOMENTUM | DESCRIPTIVE_ONLY |
| THEME_ETF_5D_MOMENTUM | DESCRIPTIVE_ONLY |
| THEME_RADAR_ATTENTION_ONLY | DESCRIPTIVE_ONLY |
| ZERO_BASE_RATE | DESCRIPTIVE_ONLY |

## 13. Data gaps

- Historical point-in-time ETF holdings are unavailable; breadth-only and T0 daily evidence are blocked.
- H1 completed runs are rehearsals with no settled forward labels and do not count as official strategy evidence.
- Historical VWAP, exact 15:45 confirmation, and exact intraday range are not interpolated into H2.
- H3 source-data cutoff is not fully reproducible and seven daily records are shifted; all H3 results remain descriptive.
- D1/D2 predictions were imported from the frozen transparent baseline. Evaluation uses new frozen 1/1 threshold folds; no model weights were refit.
- Close-origin horizons are direction labels only. They are not same-day executable return claims.

## 14. Validation protocol

The lab froze `24` expanding evaluation folds with purge=1, embargo=1 and train-only threshold selection. The imported transparent predictions were originally produced by a stricter nested 3/3 walk-forward. Comparisons use common test dates; no random date split is used.

## 15. Runtime and task boundary

The active v0.4.5 capture runtime, both Windows Scheduled Tasks, immutable real/rehearsal runs, and the frozen v0.5.0-rc2 release are read-only inputs to this branch. End-of-run hashes and task actions must match the pre-run audit before this report is accepted.

## 16. Positions and orders

`paper_positions=0`; `real_orders=0`. No Formal Data Shadow or Model Shadow authorization was created or changed.

## Full ablation table

| Comparison | Common dates | Paired mean (bps) | Paired median (bps) | Bootstrap 95% CI (bps) | Status |
|---|---:|---:|---:|---:|---|
| D0_vs_D1 | 3024 | +8.31 | +0.00 | [+3.05, +13.17] | COMPLETE_COMMON_SAMPLE |
| D1_vs_5d_relative_momentum | 3024 | +12.62 | +0.00 | [+7.45, +17.97] | COMPLETE_COMMON_SAMPLE |
| D1_vs_20d_relative_momentum | 3024 | +11.50 | +0.00 | [+6.15, +17.15] | COMPLETE_COMMON_SAMPLE |
| D1_vs_D1_plus_T | 0 | NA | NA | [NA, NA] | INSUFFICIENT_EVIDENCE |
| D1_plus_T_vs_D1_plus_T_plus_E0 | 0 | NA | NA | [NA, NA] | INSUFFICIENT_EVIDENCE |
| D1_plus_T_vs_D1_plus_T_plus_ThemeRadarAttention | 0 | NA | NA | [NA, NA] | INSUFFICIENT_EVIDENCE |
| T_plus_E_vs_T_plus_E_plus_Playbook | 0 | NA | NA | [NA, NA] | INSUFFICIENT_EVIDENCE |

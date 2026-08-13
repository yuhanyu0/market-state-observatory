# Episode Model

Episode locates the market response in `onset`, `expansion`, `retest`, `mature`,
`exhaustion`, or `reversal`. It is a sequential state estimate, not a count of
consecutive semantic theme labels.

The stable contract is model-agnostic. A future BOCPD or hidden semi-Markov model
must remain disabled until sufficient point-in-time history exists and a
walk-forward ablation demonstrates incremental value over Direction plus
Transmission. Until then the public state is `not_estimable`.

Episode uncertainty and transition invalidation must be visible. A positive
Direction estimate in exhaustion does not authorize a fresh long playbook.

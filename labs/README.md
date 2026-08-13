# Labs

Everything in this directory is experimental and disabled by default. Labs may
emit research artifacts, but they cannot alter the stable Observation,
ObserverEstimate, StateCertificate, PlaybookDecision, publication, or safety
contracts.

Current placeholders:

- `graph_ssm/`: graph state-space direction experiments
- `field_models/`: PDE and boundary-dependent transport hypotheses
- `semantic_event_observer/`: semantic and event observer research

Enabling a lab requires a new explicit feature flag, same-date ablation against
the transparent baseline, untouched test windows, and a documented pruning rule.

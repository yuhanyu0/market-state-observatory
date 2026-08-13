# Observer Registry

The registry is a capability boundary, not merely a list of models. Each
observer declares whether it is signed, decision-required, allowed to propose a
theme, and allowed to select a playbook. The default registry contains Direction,
Transmission, Episode, structural attention, Fragility, and an optional known-at
Event observer.

Theme Radar is registered only as `theme_radar_attention`. It is unsigned,
optional, cannot generate candidate themes, cannot label Direction, and cannot
gate a playbook. A registry assertion fails if any of those properties change.

Every estimate carries an as-of time, evidence references, uncertainty,
invalidation, source version/hash when applicable, and three separate booleans:

- `data_ready`: required inputs exist and pass lineage checks;
- `model_estimated`: an observer actually produced an estimate; and
- `decision_eligible`: the estimate may participate in a decision-sufficient
  certificate.

These states are deliberately non-equivalent.

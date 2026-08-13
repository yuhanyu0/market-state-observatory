# Theme Radar Observer Contract

Allowed fields are observer identity, theme identity already in the Observatory
universe, as-of time, attention state, migration/persistence interpretation,
evidence references, source version/hash, uncertainty, notes, and invalidation.

The estimate must declare `signed=false` in integration metadata. Runtime
registration also fixes `required_for_decision=false`, `may_select_theme=false`,
and `may_decide_playbook=false`. Any adapter that violates this boundary is
rejected before certificate compilation.

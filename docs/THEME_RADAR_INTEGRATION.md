# Theme Radar integration

Theme Radar remains a separate project and repository. This repository does not overwrite or subsume it.

Here, Theme Radar can contribute an isolated `theme_radar_attention` ObserverEstimate describing structural attention, migration or importance. It cannot:

- generate the candidate universe;
- define Direction labels;
- define training targets;
- override Transmission;
- directly create a playbook or trade.

Its incremental value is tested on common prospective windows:

```text
D + T
vs
D + T + Theme Radar attention
```

Disagreement is also tested as a state variable, including attention rising while Direction is negative or unresolved.

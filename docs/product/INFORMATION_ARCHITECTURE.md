# Information Architecture

The primary navigation is task ordered: Today, Themes, Evidence, Certificates,
Experiments, Data Quality, Methodology, Research, Status.

- **Today** is the operational home and contains no methodology prerequisite.
- **Themes** moves from comparable cards into one theme's state composition.
- **Evidence** is the cross-theme lineage and conflict ledger.
- **Certificates** is the printable decision-sufficiency artifact.
- **Experiments** records gates, evidence grades, and ablations.
- **Data Quality** owns capture completeness and runtime health.
- **Methodology** explains the stable evidence contract.
- **Research** contains disabled, removable modules.
- **Status** states what is running and what cannot run.

Hash routes keep static GitHub Pages deployment reliable. Theme permalinks use
`#/themes?theme=<theme_id>` and never encode private identifiers.

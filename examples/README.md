# Synthetic Reference Corpus

This directory contains public-safe synthetic examples only. It does not contain
broker data, raw provider responses, private runs, positions, orders, or evidence
of strategy performance.

`scripts/run_synthetic_demo.py` deterministically produces eight scenarios across
the complete structured path:

1. positive Direction, broad Transmission, onset;
2. rising structural attention with unresolved Direction;
3. positive Direction with narrow Transmission;
4. broad negative propagation;
5. positive but exhausted, with no chase;
6. retest continuation;
7. data blocked, with no decision; and
8. observer conflict requiring a discriminating probe.

Outputs are separated into observations, observer estimates, evidence graphs,
response modes, State Certificates, playbook decisions, and experiment records.
Every decision remains `WAIT`, `DATA_BLOCKED_NO_DECISION`, or
`MODEL_SHADOW_ONLY`. No real order is created.

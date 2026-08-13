# Playbook State Machine

A playbook is a control option with internal state, activation, invalidation, and
termination. It receives `currently_held` and `previous_state`; it is not a
stateless label attached to a chart.

The first release supports:

- `A_transition_breakout`: positive Direction, broad Transmission, early Episode;
- `B_retest_continuation`: a confirmed retest after an eligible positive state;
- `D_wait_unresolved`: missing or unresolved discriminating evidence;
- `F_overextended_no_chase`: mature extension or exhaustion; and
- `NoScript`: no supported option or a blocking state.

Actions are research-state transitions such as WAIT, HOLD, EXIT, or an ENTER
inside Model Shadow. The package has no broker client and cannot create orders.

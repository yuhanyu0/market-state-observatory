# Active Observation and Next Probe

The Observatory does not merely classify the present. When evidence is
insufficient, it names the cheapest next observation likely to change the state.
Each `NextProbe` specifies:

- what must be acquired;
- exactly two candidate states it distinguishes;
- the latest legal acquisition time;
- expected information value;
- acquisition cost and latency; and
- why the current certificate depends on it.

Examples include testing whether attention has selected a sign, whether a leader
has propagated to the rest of the basket, or whether an extension resolves into
an orderly retest. Missed point-in-time observations are marked missed. They are
not reconstructed after the fact.

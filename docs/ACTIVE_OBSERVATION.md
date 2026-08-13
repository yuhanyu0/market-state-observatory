# Active observation and next probes

Waiting can be an active decision when a near-term observation has high expected value of information.

Conceptually:

```text
VOI(q) = E[max_a U(a | state, q)] - max_a E[U(a | state)] - cost(q)
```

Examples:

- attention rising, Direction unresolved → wait for 15:45 relative strength, VWAP and breadth;
- Direction positive, Transmission narrow → inspect leader concentration and rest-of-basket propagation;
- Direction positive, Episode ambiguous → wait for an orderly retest and observe whether breadth survives.

The first implementation is rule-based. Future probabilistic VOI models must be validated separately.

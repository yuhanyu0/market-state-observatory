# Market State Observatory v0.5.1-rc1

Status: candidate release built for review; not selected or scheduled.

## Scope

- `PROSPECTIVE_CANDIDATE_SHADOW` freezes candidate evidence before outcomes while remaining `decision_eligible=false` and counterfactual only.
- Preclose candidates read only immutable open, 15:30, and 15:45 evidence. A separate 15:47 Alpaca SIP data quote must follow candidate generation.
- Postclose candidates consume the completed 16:15 Daily Report and cannot claim same-day close execution.
- Signals and outcomes use separate append-only ledgers. Settlement is sidecar-only, idempotent, and never mutates a completed run.
- Theme ETF is the only enabled vehicle. Basket, torque, C2, broker clients, positions, and orders remain disabled.

## Research closure

The final frozen H2 rank diagnostic found no robust after-cost 3d/5d cross-theme result. Historical D0/D1/D2 models remain retired under `MODEL_DISPOSITION_V1.json`, and `H2_MODEL_MINING_CLOSED=true`.

## Safety

The active v0.4.5 capture release and the frozen v0.5.0-rc2 Daily Report release are unchanged. `MSO-Preclose-Candidate-Shadow` is not installed. Formal Data Shadow and Model Shadow remain unstarted, with zero paper positions and zero real orders.

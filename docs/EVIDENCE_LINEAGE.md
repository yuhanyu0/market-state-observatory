# Evidence lineage snapshot

This document records why the project was separated from a simple Theme Radar-to-trade pipeline.

## Internal historical findings, 2026-08

- Midday Theme Radar evidence was more consistent with **attention / volatility activation** than confirmed bullish direction.
- A universal fixed high-torque mapping did not add alpha and amplified downside risk.
- The clean narrow-theme C2 hypothesis had zero eligible historical strategy events and remained prospective-only.
- A Source-Native transparent historical daily baseline did not show a robust investable edge: next-open to next-close was negative after 10 bps, while the three-day point estimate was small and uncertain.
- The first Alpaca SIP smoke test passed for seven core ETFs with a maximum quote age of 16.947581 seconds; the integration reported 124 passing tests.

These findings justify the current architecture: independent observers, point-in-time prospective evidence, incremental ablation and explicit no-decision states.

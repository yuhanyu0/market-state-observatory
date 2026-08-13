# New repository instructions

Recommended repository:

```text
yuhanyu0/market-state-observatory
```

This is a standalone project. Do not place it inside or overlay it onto `theme-radar-log`.

1. Extract the ZIP into a new directory.
2. Review `LICENSE_DECISION.md`.
3. Run `pip install -e .[dev]`, `pytest`, and `python scripts/validate_repo.py`.
4. Preview with `python scripts/serve.py`.
5. Run `scripts/bootstrap_new_repo.ps1` from the new directory.
6. Enable GitHub Pages using GitHub Actions if requested.

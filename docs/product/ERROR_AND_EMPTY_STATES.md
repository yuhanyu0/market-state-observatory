# Error and Empty States

| State | User-facing response | Prohibited fallback |
|---|---|---|
| public JSON unavailable | name resource class, Retry | private runtime read |
| scheduled point missed | missed, not backfilled | daily close substitution |
| Direction not estimated | Not estimated | positive/negative from readiness |
| Episode history short | sequence requirement | reconstructed labels |
| membership incomplete | Transmission blocked | current holdings lookback |
| credential absent | PRESENT/ABSENT status | credential value in error |
| publisher audit fails | no commit or push | partial public update |
| no eligible action | blocked certificate | BUY/SELL copy |

from __future__ import annotations

import json
import sys

from .alpaca_adapter import AlpacaSIPAdapter
from .credential_loader import safe_credential_status


def main() -> int:
    print(safe_credential_status())
    try:
        result = AlpacaSIPAdapter().latest_quotes(["SPY"])
    except Exception as error:
        print(f"ALPACA_SIP_CONNECTIVITY=FAIL error_type={type(error).__name__}")
        return 1
    print(
        json.dumps(
            {
                "ALPACA_SIP_CONNECTIVITY": "PASS",
                "response_status": result.response_status,
                "provider_request_id": "PRESENT" if result.provider_request_id else "ABSENT",
                "feed": "sip",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

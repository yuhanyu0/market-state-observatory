from __future__ import annotations

import argparse
import json
from pathlib import Path

from market_state_observatory.publication import write_public_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Import an already-redacted State Certificate")
    parser.add_argument("certificate", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(args.certificate.read_text(encoding="utf-8"))
    destination = root / "public" / "data" / "certificates" / args.certificate.name
    print(write_public_json(payload, "state_certificate", destination, root))


if __name__ == "__main__":
    main()

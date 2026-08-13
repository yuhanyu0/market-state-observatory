from __future__ import annotations

import argparse
import json
from pathlib import Path

from market_state_observatory.publication import write_public_json
from market_state_observatory.redaction import validate_already_redacted
from market_state_observatory.validation import validate_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Import an already-redacted rehearsal summary")
    parser.add_argument("summary", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(args.summary.read_text(encoding="utf-8"))
    validate_already_redacted(payload)
    validate_payload(payload, "rehearsal_summary", root)
    date = payload["trading_date"]
    public_path = write_public_json(payload, "rehearsal_summary", root / "public" / "data" / "experiments" / f"day0b-{date}.json", root)
    site_detail = public_path
    aggregate = [payload]
    validate_already_redacted(aggregate)
    aggregate_path = root / "public" / "data" / "experiments.json"
    aggregate_path.write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "public": str(public_path), "site": str(site_detail), "aggregate": str(aggregate_path)}, sort_keys=True))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
from pathlib import Path

from market_state_observatory.publication.runtime_publisher import publish_quality_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish fail-closed redacted runtime quality")
    parser.add_argument("quality", type=Path)
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = publish_quality_snapshot(repository=root, quality_path=args.quality, push=args.push)
    print(f"PUBLICATION_RESULT={result}")
    print("RAW_MARKET_DATA_PUBLISHED=false")
    print("PAPER_POSITIONS=0")
    print("REAL_ORDERS=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

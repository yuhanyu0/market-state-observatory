from __future__ import annotations

import json
from pathlib import Path

from market_state_observatory.publication import write_public_json


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    status = json.loads((root / "examples" / "publication_status.json").read_text(encoding="utf-8"))
    output = write_public_json(status, "publication_status", root / "public" / "data" / "status.json", root)
    print(output)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
from pathlib import Path

from market_state_observatory.publisher import publish_status

p = argparse.ArgumentParser()
p.add_argument("status", type=Path)
p.add_argument("--site", type=Path, default=Path("site"))
a = p.parse_args()
print(publish_status(a.status, a.site))

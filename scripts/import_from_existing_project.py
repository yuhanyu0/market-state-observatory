from __future__ import annotations

import argparse
import shutil
from pathlib import Path

WHITELIST = {
    "backtest/SOURCE_NATIVE_DATA_SCHEMA.md": "docs/archive/SOURCE_NATIVE_DATA_SCHEMA.md",
    "backtest/SOURCE_NATIVE_DATA_READINESS_REPORT.md": "docs/archive/SOURCE_NATIVE_DATA_READINESS_REPORT.md",
    "backtest/HISTORICAL_DAILY_BASELINE_REPORT.md": "docs/archive/HISTORICAL_DAILY_BASELINE_REPORT.md",
    "backtest/THEME_RADAR_CONCEPTUAL_BLIND_SPOTS.md": "docs/archive/THEME_RADAR_CONCEPTUAL_BLIND_SPOTS.md",
}
FORBIDDEN_PARTS = {"logs", "assets", "raw", "data_shadow", "model_shadow", "orders", "positions", "credentials", "secrets"}

parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--destination", type=Path, default=Path(__file__).resolve().parents[1])
parser.add_argument("--apply", action="store_true")
args = parser.parse_args()

for src_rel, dst_rel in WHITELIST.items():
    if FORBIDDEN_PARTS.intersection(Path(src_rel).parts):
        raise SystemExit(f"Refusing forbidden path: {src_rel}")
    src = args.source / src_rel
    dst = args.destination / dst_rel
    print(f"{src} -> {dst} {'COPY' if args.apply else 'DRY-RUN'}")
    if args.apply and src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

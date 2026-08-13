from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


class LocalAssetParser(HTMLParser):
    def __init__(self, source: Path, root: Path) -> None:
        super().__init__()
        self.source = source
        self.root = root
        self.findings: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        for key in ("href", "src"):
            value = attributes.get(key)
            if not value or value.startswith(("#", "data:", "mailto:")):
                continue
            parsed = urlparse(value)
            if parsed.scheme or parsed.netloc:
                continue
            target = (self.source.parent / parsed.path).resolve()
            if target != self.root.resolve() and self.root.resolve() not in target.parents:
                self.findings.append(f"{self.source.name}: path escapes build: {value}")
            elif not target.exists():
                self.findings.append(f"{self.source.name}: missing asset {value}")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    build = root / "dist" / "web"
    findings: list[str] = []
    index = build / "index.html"
    if not index.is_file():
        findings.append("dist/web/index.html is missing; run npm run build")
    else:
        parser = LocalAssetParser(index, build)
        parser.feed(index.read_text(encoding="utf-8"))
        findings.extend(parser.findings)
    for data in sorted((root / "public" / "data").rglob("*.json")):
        try:
            json.loads(data.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            findings.append(f"{data.relative_to(root)}: invalid JSON ({type(error).__name__})")
    app = (root / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    routes = ("today", "themes", "evidence", "certificates", "experiments", "data-quality", "methodology", "research", "status")
    findings.extend(f"missing product route: {route}" for route in routes if f'"{route}"' not in app)
    if findings:
        raise SystemExit("FAIL\n" + "\n".join(findings))
    print(f"PASS: React entry, {len(routes)} routes, local assets, and public JSON")


if __name__ == "__main__":
    main()

from pathlib import Path

from scripts.check_site_links import LocalAssetParser


def parse_html(index: Path, root: Path, html: str) -> list[str]:
    parser = LocalAssetParser(index, root)
    parser.feed(html)
    return parser.findings


def test_local_asset_parser_accepts_existing_assets(tmp_path: Path) -> None:
    index = tmp_path / "index.html"
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("", encoding="utf-8")
    assert parse_html(index, tmp_path, '<script src="assets/app.js"></script>') == []


def test_local_asset_parser_rejects_missing_or_escaping_assets(tmp_path: Path) -> None:
    index = tmp_path / "index.html"
    findings = parse_html(
        index,
        tmp_path,
        '<script src="assets/missing.js"></script><a href="../private.json">private</a>',
    )
    assert any("missing asset" in finding for finding in findings)
    assert any("path escapes build" in finding for finding in findings)

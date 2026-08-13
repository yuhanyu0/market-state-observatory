from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


def test_all_required_pages_exist() -> None:
    required = {"index.html", "observatory.html", "themes.html", "certificates.html", "experiments.html", "architecture.html", "methodology.html", "validation.html", "research.html", "roadmap.html", "glossary.html", "status.html", "about.html", "404.html"}
    assert required <= {path.name for path in SITE.glob("*.html")}


def test_site_has_no_mojibake() -> None:
    bad = ("\u00e2", "\u00c3", "\u00c2")
    for path in SITE.rglob("*"):
        if path.is_file() and path.suffix in {".html", ".js", ".css", ".json"}:
            text = path.read_text(encoding="utf-8")
            assert not any(token in text for token in bad), path


def test_home_has_full_bleed_evidence_canvas() -> None:
    home = (SITE / "index.html").read_text(encoding="utf-8")
    assert 'id="evidence-canvas"' in home
    assert "Market State Observatory" in home


def test_site_exposes_research_states_not_live_advice() -> None:
    text = "\n".join(path.read_text(encoding="utf-8") for path in SITE.glob("*.html"))
    assert "MODEL_SHADOW_ONLY" in text
    assert "Real orders" in text
    assert "live trading enabled" not in text.lower()


def test_site_json_is_parseable() -> None:
    for path in (SITE / "data").rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))


def test_synthetic_certificate_index_has_eight_entries() -> None:
    index = json.loads((SITE / "data" / "synthetic_index.json").read_text(encoding="utf-8"))
    assert len(index) == 8


def test_theme_certificates_use_v040_contract() -> None:
    from market_state_observatory.validation import validate_payload

    for path in (SITE / "data" / "certificates").glob("*.json"):
        validate_payload(json.loads(path.read_text(encoding="utf-8")), "state_certificate", ROOT)

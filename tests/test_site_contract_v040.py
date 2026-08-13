from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
PUBLIC_DATA = ROOT / "public" / "data"


def test_all_required_product_routes_exist() -> None:
    app = (WEB / "src" / "App.tsx").read_text(encoding="utf-8")
    routes = {
        "today",
        "themes",
        "evidence",
        "certificates",
        "experiments",
        "data-quality",
        "methodology",
        "research",
        "status",
    }
    assert all(f'["{route}"' in app for route in routes)


def test_product_sources_have_no_mojibake() -> None:
    bad = ("\u00c2", "\u00c3", "\u00e2\u20ac")
    roots = (WEB, PUBLIC_DATA)
    for root in roots:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".html", ".tsx", ".ts", ".css", ".json"}:
                text = path.read_text(encoding="utf-8")
                assert not any(token in text for token in bad), path


def test_today_has_evidence_canvas() -> None:
    app = (WEB / "src" / "App.tsx").read_text(encoding="utf-8")
    graph = (WEB / "src" / "components" / "EvidenceGraph.tsx").read_text(encoding="utf-8")
    assert "<EvidenceGraph />" in app
    assert "Market State Observatory" in app
    assert "<canvas" in graph


def test_product_exposes_research_states_not_live_advice() -> None:
    app = (WEB / "src" / "App.tsx").read_text(encoding="utf-8")
    status = json.loads((PUBLIC_DATA / "status.json").read_text(encoding="utf-8"))
    assert "NO BUY / SELL OUTPUT" in app
    assert status["model_shadow_started"] is False
    assert status["paper_positions"] == 0
    assert status["real_orders"] == 0


def test_public_json_is_parseable() -> None:
    for path in PUBLIC_DATA.rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))


def test_synthetic_certificate_corpus_has_eight_entries() -> None:
    certificates = list((PUBLIC_DATA / "synthetic_certificates").glob("*.json"))
    assert len(certificates) == 8


def test_theme_certificates_use_v040_contract() -> None:
    from market_state_observatory.validation import validate_payload

    for path in (PUBLIC_DATA / "certificates").glob("*.json"):
        validate_payload(json.loads(path.read_text(encoding="utf-8")), "state_certificate", ROOT)

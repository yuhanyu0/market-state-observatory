from __future__ import annotations

import json
import shutil
from pathlib import Path

from market_state_observatory.redaction import validate_already_redacted
from market_state_observatory.validation import validate_payload

NAV = (
    ("index.html", "Overview"),
    ("observatory.html", "Observatory"),
    ("themes.html", "Themes"),
    ("certificates.html", "Certificates"),
    ("experiments.html", "Experiments"),
    ("architecture.html", "Architecture"),
    ("validation.html", "Validation"),
    ("research.html", "Research"),
    ("roadmap.html", "Roadmap"),
    ("glossary.html", "Glossary"),
    ("status.html", "Status"),
    ("about.html", "About"),
)


def nav(active: str) -> str:
    links = "".join(
        f'<a href="{href}"' + (' aria-current="page"' if href == active else "") + f'>{label}</a>'
        for href, label in NAV
    )
    return f'''<a class="skip" href="#content">Skip to content</a><nav class="site-nav"><div class="wrap nav-inner"><a class="brand" href="index.html"><img src="assets/logo.svg" alt="">Market State Observatory</a><div class="nav-links" aria-label="Primary navigation">{links}</div></div></nav>'''


def footer() -> str:
    return '''<footer class="footer"><div class="wrap footer-grid"><span>Point-in-time public research infrastructure</span><span>No live trading &middot; no broker execution &middot; <span id="updated">status pending</span></span></div></footer><script src="app.js"></script>'''


def page(filename: str, title: str, eyebrow: str, lead: str, content: str) -> str:
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><meta name="description" content="{lead}"><title>{title} | Market State Observatory</title><link rel="stylesheet" href="styles.css"></head><body>{nav(filename)}<header class="page-head"><div class="wrap"><div class="eyebrow">{eyebrow}</div><h1 class="page-title">{title}</h1><p class="lead">{lead}</p></div></header><main id="content">{content}</main>{footer()}</body></html>'''


def section(body: str) -> str:
    return f'<section><div class="wrap">{body}</div></section>'


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    site = root / "site"
    home = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><meta name="description" content="Auditable evidence-state infrastructure for incomplete market observers."><title>Market State Observatory</title><link rel="stylesheet" href="styles.css"></head><body>{nav("index.html")}<header class="hero"><canvas class="hero-canvas" id="evidence-canvas" aria-hidden="true"></canvas><div class="wrap hero-content"><div class="eyebrow">Evidence before action</div><h1>Market State Observatory</h1><p class="lead">Multiple incomplete observers become an auditable evidence state, response mode, State Certificate, and stateful research playbook. Missing evidence remains visible.</p><div class="status-strip"><span class="status-chip ok">SIP <b id="sip-status">loading</b></span><span class="status-chip warn">Data Shadow <b id="data-gate">0/20</b></span><span class="status-chip">MODEL_SHADOW_ONLY off</span><span class="status-chip">Real orders 0</span></div></div></header><main id="content">'''
    home += section('''<h2>Current evidence boundary</h2><p class="section-lead">The 2026-08-10 rehearsal validates a public-safe afternoon measurement chain. It does not validate market direction or strategy performance.</p><div class="grid"><div class="card span-3"><div class="label">Core SIP symbols</div><div class="metric" id="core-symbols">--</div><div class="small">SPY and six frozen theme ETFs</div></div><div class="card span-3"><div class="label">Captured records</div><div class="metric" id="captured">--</div><div class="small">Day 0B planned denominator</div></div><div class="card span-3"><div class="label">Direction data-ready</div><div class="metric" id="direction-ready">--</div><div class="small">At 15:45; not a sign</div></div><div class="card span-3"><div class="label">Collector tests</div><div class="metric" id="collector-tests">--</div><div class="small">Source collector report</div></div></div><p class="boundary"><b>Data-ready does not mean bullish.</b> Rehearsal does not count as strategy evidence.</p>''')
    home += section('''<h2>Evidence-state chain</h2><p class="section-lead">Facts, inference, interpretation, playbook choice, and execution evidence remain separate objects.</p><div class="flow"><div class="flow-step"><b>Observers</b><span class="small">Independent, versioned, uncertain views.</span></div><div class="flow-step"><b>Evidence</b><span class="small">Support, conflict, lineage, invalidation.</span></div><div class="flow-step"><b>Response mode</b><span class="small">Sign, breadth, propagation, lifecycle.</span></div><div class="flow-step"><b>Certificate</b><span class="small">Decision sufficiency and next probe.</span></div><div class="flow-step"><b>Playbook</b><span class="small">Stateful research option; no broker action.</span></div></div>''')
    home += section('''<h2>Three product surfaces</h2><div class="grid"><article class="card span-4"><div class="label">Personal</div><h3>Personal Investment Cockpit</h3><p class="small">Auditable states, invalidation, and next probes without hiding uncertainty.</p></article><article class="card span-4"><div class="label">Public</div><h3>Market Response Observatory</h3><p class="small">Response modes, propagation, lifecycle, and observer disagreement.</p></article><article class="card span-4"><div class="label">General</div><h3>General Evidence-State Engine</h3><p class="small">A reusable pattern for incomplete observers and decision boundaries.</p></article></div>''')
    home += f'''</main>{footer()}</body></html>'''

    pages = {
        "index.html": home,
        "observatory.html": page("observatory.html", "Observatory", "Public-safe state view", "Six frozen themes, independent observers, disagreement, next probes, and validation state.", section('''<div id="theme-tabs" class="theme-tabs" role="tablist" aria-label="Frozen themes"></div><div class="grid"><div class="span-4"><div class="card"><div class="label">Selected theme</div><div class="metric" id="selected-theme">--</div><p>ETF <b id="selected-etf">--</b></p><p>Status <span class="state-pill warn" id="certificate-status">loading</span></p><p class="small"><b>Next probe</b><br><span id="next-probe">--</span></p></div></div><pre class="certificate span-8" id="certificate-json">Loading public certificate...</pre></div>''') + section('''<h2>Observer disagreement</h2><p class="section-lead">The public view preserves conflicts rather than blending them into an opaque score.</p><div class="table-wrap"><table><thead><tr><th>Observer</th><th>Question</th><th>Decision role</th></tr></thead><tbody><tr><td>Direction</td><td>What is the signed market-relative release?</td><td>Required</td></tr><tr><td>Transmission</td><td>Has the move propagated beyond one name?</td><td>Required</td></tr><tr><td>Episode</td><td>Where is the response lifecycle?</td><td>Required when estimable</td></tr><tr><td>Theme Radar</td><td>Is structural attention changing?</td><td>External benchmark only</td></tr><tr><td>Fragility</td><td>What can invalidate execution quality?</td><td>Can block</td></tr><tr><td>Event</td><td>What known-at event context exists?</td><td>Disabled until sourced</td></tr></tbody></table></div>''')),
        "themes.html": page("themes.html", "Frozen themes", "Semantic prior, dynamic response", "The six-theme universe fixes ETFs, benchmarks, and baskets while treating response mode as the more basic primitive.", section('''<div class="grid"><article class="card span-4"><h3>Semiconductors</h3><p>SMH &middot; SPY &middot; frozen basket</p></article><article class="card span-4"><h3>Cloud Computing</h3><p>SKYY &middot; SPY &middot; frozen basket</p></article><article class="card span-4"><h3>Cybersecurity</h3><p>CIBR &middot; SPY &middot; frozen basket</p></article><article class="card span-4"><h3>Uranium and Nuclear</h3><p>URA &middot; SPY &middot; frozen basket</p></article><article class="card span-4"><h3>Solar Energy</h3><p>TAN &middot; SPY &middot; frozen basket</p></article><article class="card span-4"><h3>Commercial Space</h3><p>UFO &middot; SPY &middot; frozen basket</p></article></div>''') + section('''<h2>Boundary</h2><p class="boundary">A semantic theme does not guarantee common direction, propagation, episode, or risk. Point-in-time membership is required for Transmission. Current constituents are never used to reconstruct historical breadth.</p>''')),
        "certificates.html": page("certificates.html", "State Certificates", "Facts, inference, action", "Synthetic reference certificates show why a state is or is not decision-sufficient.", section('''<label for="certificate-select"><b>Synthetic scenario</b></label><select id="certificate-select" class="theme-tab"></select><div class="facts-inference-action" style="margin-top:18px"><div class="fia"><div class="label">Facts</div><pre id="cert-facts"></pre></div><div class="fia"><div class="label">Inference</div><pre id="cert-inference"></pre></div><div class="fia"><div class="label">Action boundary</div><pre id="cert-action"></pre></div></div>''') + section('''<div class="grid"><div class="card span-4"><h3>Why</h3><p id="cert-why" class="small"></p></div><div class="card span-4"><h3>Why not</h3><p id="cert-why-not" class="small"></p></div><div class="card span-4"><h3>What changes my mind</h3><p id="cert-changes" class="small"></p></div></div>''')),
        "experiments.html": page("experiments.html", "Experiments", "Prospective evidence log", "Infrastructure readiness and model evidence are reported on separate tracks.", section('''<div class="grid"><div class="card span-3"><div class="label">Day 0B</div><div class="metric" id="experiment-status">--</div></div><div class="card span-3"><div class="label">Valid / planned</div><div class="metric" id="captured">--</div></div><div class="card span-3"><div class="label">Direction inputs</div><div class="metric">6/6</div></div><div class="card span-3"><div class="label">Transmission inputs</div><div class="metric">6/6</div></div></div><p class="boundary"><b>Data-ready does not mean bullish.</b> This rehearsal does not count as strategy evidence or toward the 20-day gate.</p>''') + section('''<h2>Day 0B timeline</h2><div class="timeline"><div class="time">09:30</div><div class="event">Missed intentionally; no reconstruction.</div><div class="time">12:00</div><div class="event">Missed intentionally; no reconstruction.</div><div class="time">15:30</div><div class="event">SIP quote, trade, minute-bar, VWAP, and cumulative-volume chain captured.</div><div class="time">15:45</div><div class="event">All six theme input sets reached Direction and Transmission data readiness.</div><div class="time">Close</div><div class="event">Provider regular-session diagnostics completed; no position or order created.</div></div>''') + section('''<h2>Theme readiness</h2><div class="table-wrap"><table><thead><tr><th>Theme</th><th>ETF</th><th>15:30 age</th><th>15:45 age</th><th>Direction data</th><th>Transmission data</th><th>Episode</th><th>C2</th></tr></thead><tbody id="experiment-themes"></tbody></table></div>''')),
        "architecture.html": page("architecture.html", "Architecture", "From evidence to control option", "A five-layer state chain preserves uncertainty, disagreement, provenance, and invalidation.", section('''<div class="flow"><div class="flow-step"><b>Direction</b><span class="small">Signed market-relative release.</span></div><div class="flow-step"><b>Transmission</b><span class="small">Breadth and propagation.</span></div><div class="flow-step"><b>Episode</b><span class="small">Sequential lifecycle state.</span></div><div class="flow-step"><b>Playbook</b><span class="small">Stateful option with invalidation.</span></div><div class="flow-step"><b>Vehicle</b><span class="small">Risk-normalized expression.</span></div></div>''') + section('''<div class="grid"><article class="card span-4"><h3>Evidence graph</h3><p class="small">References, support, contradiction, lineage, and unknowns remain explicit.</p></article><article class="card span-4"><h3>Response mode</h3><p class="small">Sign and propagation are more basic than a fixed semantic theme label.</p></article><article class="card span-4"><h3>Public boundary</h3><p class="small">Only validated, redacted JSON enters this site.</p></article></div>''')),
        "methodology.html": page("methodology.html", "Methodology", "Point-in-time and falsifiable", "The research protocol requires same-date ablation, untouched windows, costs, and explicit evidence grades.", section('''<h2>Five separations</h2><ol class="list"><li>Facts are timestamped observations.</li><li>Observer inference exposes uncertainty.</li><li>State interpretation preserves conflict.</li><li>Playbook decisions know prior state and current holding.</li><li>Execution evidence remains separate and is absent from this public release.</li></ol>''') + section('''<h2>Validation protocol</h2><p>Use nested walk-forward evaluation, purge and embargo, episode-clustered and time-block bootstrap, theme fixed effects, train-only thresholds, untouched test windows, spreads and costs, point-in-time membership, and no post-close reconstruction.</p>''')),
        "validation.html": page("validation.html", "Validation ladder", "Complexity must earn its place", "Each layer is tested as an incremental same-date ablation before it can remain enabled.", section('''<div class="table-wrap"><table><thead><tr><th>Stage</th><th>Purpose</th><th>Current status</th></tr></thead><tbody><tr><td>Rehearsal</td><td>Collector integrity</td><td>Day 0B partial PASS</td></tr><tr><td>Data Shadow</td><td>20 valid point-in-time days</td><td>0/20, not started</td></tr><tr><td>D</td><td>Transparent signed Direction</td><td>Not prospectively validated</td></tr><tr><td>D + T</td><td>Transmission increment</td><td>Not enabled</td></tr><tr><td>D + T + E</td><td>Episode increment</td><td>Not enabled</td></tr><tr><td>D + T + E + P</td><td>Stateful holding</td><td>Not enabled</td></tr><tr><td>Vehicle ablation</td><td>ETF, Basket, overlay</td><td>Overlay disabled</td></tr><tr><td>Micro-live gate</td><td>Separate governance decision</td><td>Closed</td></tr></tbody></table></div>''')),
        "research.html": page("research.html", "Research agenda", "Questions before models", "The project studies disagreement, response modes, decision sufficiency, active observation, and reflexive memory.", section('''<div class="grid"><article class="card span-4"><h3>Observer disagreement</h3><p class="small">When do conflicts reveal transitions rather than noise?</p></article><article class="card span-4"><h3>Decision-sufficient state</h3><p class="small">What is the smallest evidence set that changes a research action?</p></article><article class="card span-4"><h3>Active observation</h3><p class="small">Which next probe has the highest information value per delay?</p></article><article class="card span-4"><h3>Boundary transport</h3><p class="small">How do shocks cross supply-chain and liquidity boundaries?</p></article><article class="card span-4"><h3>Response operator</h3><p class="small">Can response modes transfer across semantic themes?</p></article><article class="card span-4"><h3>Evidence-state engine</h3><p class="small">Which contracts generalize beyond markets?</p></article></div>''')),
        "roadmap.html": page("roadmap.html", "100-day roadmap", "Measurement before activation", "The next hundred days move from data integrity to incremental validation without enabling live execution.", section('''<div class="timeline"><div class="time">Days 1-20</div><div class="event">Point-in-time Data Shadow and quality gate only.</div><div class="time">Days 21-40</div><div class="event">Transparent Direction calibration and same-date momentum comparison.</div><div class="time">Days 41-60</div><div class="event">Transmission and Episode ablations, if data gates pass.</div><div class="time">Days 61-80</div><div class="event">Model Shadow for the five frozen playbooks.</div><div class="time">Days 81-100</div><div class="event">Vehicle ablation, publication review, and pruning.</div></div>''')),
        "glossary.html": page("glossary.html", "Glossary", "Stable language", "Terms are defined to prevent readiness, inference, and action from collapsing into one label.", section('''<div class="table-wrap"><table><tbody><tr><th>Data ready</th><td>Required inputs exist and pass lineage checks.</td></tr><tr><th>Model estimated</th><td>An observer produced an estimate.</td></tr><tr><th>Decision eligible</th><td>An estimate may enter a decision-sufficient certificate.</td></tr><tr><th>Response mode</th><td>A pattern of sign, support, propagation, lifecycle, and fragility.</td></tr><tr><th>State Certificate</th><td>Structured facts, inference, conflict, invalidation, and next probe.</td></tr><tr><th>Structural attention</th><td>Unsigned importance or migration evidence from an external observer.</td></tr><tr><th>Torque</th><td>A risk-normalized incremental overlay, not a fixed story stock.</td></tr><tr><th>NoScript</th><td>No supported playbook under the current evidence state.</td></tr></tbody></table></div>''')),
        "status.html": page("status.html", "Project status", "Public evidence boundary", "Current status is infrastructure readiness with Data Shadow and Model Shadow not started.", section('''<div class="grid"><div class="card span-3"><div class="label">Mode</div><div class="metric" id="status-mode">--</div></div><div class="card span-3"><div class="label">Data Shadow</div><div class="metric" id="data-gate">0/20</div></div><div class="card span-3"><div class="label">Model Shadow</div><div class="metric">OFF</div></div><div class="card span-3"><div class="label">Real orders</div><div class="metric">0</div></div></div>''') + section('''<h2>Publication state</h2><p class="boundary">No private provider payload, account field, position, order, Data Shadow run, or Model Shadow run is published. Data-ready does not mean bullish.</p>''')),
        "about.html": page("about.html", "About", "Independent public project", "Market State Observatory is independent of Theme Radar and exposes evidence-state contracts, not live investment advice.", section('''<div class="grid"><article class="card span-6"><h3>Independence</h3><p>The project does not modify or depend on the Theme Radar repository. Theme Radar may appear only through a redacted structural-attention observer contract.</p></article><article class="card span-6"><h3>LLM boundary</h3><p>An LLM may render a validated State Certificate in natural language. It may not create facts, repair missing observations, or override eligibility.</p></article></div>''') + section('''<h2>Version 0.4.0</h2><p>Typed contracts, 16 Draft 2020-12 schemas, a public-safe synthetic corpus, a static Observatory site, and fail-closed publication bridges.</p>''')),
        "404.html": page("404.html", "Page not found", "404", "The requested public page does not exist.", section('''<p><a class="theme-tab" href="index.html">Return to the Observatory overview</a></p>''')),
    }

    for filename, content in pages.items():
        (site / filename).write_text(content, encoding="utf-8")

    synthetic_source = root / "examples" / "state_certificates"
    synthetic_target = site / "data" / "synthetic_certificates"
    synthetic_target.mkdir(parents=True, exist_ok=True)
    index = []
    for source in sorted(synthetic_source.glob("*.json")):
        payload = json.loads(source.read_text(encoding="utf-8"))
        validate_already_redacted(payload)
        validate_payload(payload, "state_certificate", root)
        destination = synthetic_target / source.name
        shutil.copyfile(source, destination)
        index.append({"id": source.stem, "label": source.stem.replace("_", " ").title(), "path": f"data/synthetic_certificates/{source.name}"})
    (site / "data" / "synthetic_index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")

    themes = json.loads((site / "data" / "themes.json").read_text(encoding="utf-8"))["themes"]
    base_certificate = json.loads(
        (root / "examples" / "state_certificates" / "data_blocked.json").read_text(
            encoding="utf-8"
        )
    )
    theme_certificate_dir = site / "data" / "certificates"
    theme_certificate_dir.mkdir(parents=True, exist_ok=True)
    for theme in themes:
        certificate = json.loads(json.dumps(base_certificate))
        certificate["certificate_id"] = f"public-synthetic-{theme['theme_id']}-v040"
        certificate["theme_id"] = theme["theme_id"]
        certificate["facts"] = [
            {
                "kind": "boundary",
                "text": "Synthetic public certificate; no current live state is published.",
            },
            {
                "kind": "infrastructure",
                "text": "Day 0B input readiness does not encode signed Direction.",
            },
        ]
        if certificate["next_probe"] is not None:
            certificate["next_probe"]["theme_id"] = theme["theme_id"]
            certificate["next_probe"]["probe_id"] = f"{theme['theme_id']}-data-completion"
        validate_already_redacted(certificate)
        validate_payload(certificate, "state_certificate", root)
        (theme_certificate_dir / f"{theme['theme_id']}.json").write_text(
            json.dumps(certificate, indent=2) + "\n", encoding="utf-8"
        )

    urls = "\n".join(f"  <url><loc>https://yuhanyu0.github.io/market-state-observatory/{href}</loc></url>" for href, _ in NAV)
    (site / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>\n', encoding="utf-8")
    print(json.dumps({"status": "PASS", "pages": len(pages), "synthetic_certificates": len(index)}, sort_keys=True))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

from market_state_observatory.analysis.model_disposition import ModelDispositionRegistry
from market_state_observatory.analysis.prospective_candidate import (
    distinct_date_gate_status,
    read_ndjson,
)
from market_state_observatory.analysis.prospective_settlement import summarize_outcomes

from .notifications import load_recent_alerts
from .observation_freezer import canonical_json, write_exclusive
from .process_ownership import process_truth
from .quality_engine import evaluate_run_quality
from .runtime_paths import RuntimePaths, resolve_runtime_paths

HOST = "127.0.0.1"


def _latest_file(root: Path, pattern: str) -> Path | None:
    rows = sorted(root.rglob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    return rows[0] if rows else None


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _scheduler_status() -> dict[str, object]:
    if os.name != "nt":
        return {"state": "UNAVAILABLE_NON_WINDOWS"}
    states: dict[str, str] = {}
    for name in (
        "MSO-Daily-Rehearsal",
        "MSO-Daily-Formal",
        "MSO-Daily-Report",
        "MSO-Preclose-Candidate-Shadow",
    ):
        result = subprocess.run(
            ["schtasks.exe", "/Query", "/TN", name, "/FO", "LIST"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        states[name] = "INSTALLED" if result.returncode == 0 else "NOT_INSTALLED"
    return {"state": "CHECKED", "tasks": states}


def operator_state(paths: RuntimePaths) -> dict[str, Any]:
    runtime_status = _load_json(_latest_file(paths.operator, "runtime_status*.json")) or {}
    quality_candidates = [
        path
        for root in (paths.data_shadow, paths.observations)
        if root.exists()
        for path in root.rglob("DATA_QUALITY.json")
    ]
    quality_path = max(quality_candidates, key=lambda path: path.stat().st_mtime) if quality_candidates else None
    report_path = _latest_file(paths.root / "analysis", "OBSERVATION_REPORT.json")
    incident_path = _latest_file(paths.root / "analysis", "INCIDENT_SUMMARY.json")
    report = _load_json(report_path) or {}
    quality = _load_json(quality_path) or {}
    process_state = process_truth(paths.operator)
    formal_quality = [
        _load_json(path) or {}
        for path in paths.data_shadow.rglob("DATA_QUALITY.json")
    ] if paths.data_shadow.exists() else []
    rehearsal_quality = [
        _load_json(path) or {}
        for path in paths.observations.rglob("DATA_QUALITY.json")
    ] if paths.observations.exists() else []
    rehearsal_runs = list(paths.observations.rglob("RUN.json")) if paths.observations.exists() else []
    capture_pipeline_pass = bool(
        quality.get("process_success")
        and float(quality.get("observation_capture_rate") or 0) >= 0.95
        and int(quality.get("future_timestamp_count") or 0) == 0
        and int(quality.get("backfill_count") or 0) == 0
    )
    report_health = report.get("sections", {}).get("G_system_health", {})
    decision_quote_count = int(report_health.get("decision_primary_quote_count") or 0)
    decision_stale_count = int(report_health.get("decision_stale_quote_count") or 0)
    decision_feed_pass = decision_quote_count > 0 and decision_stale_count == 0
    decision_status = report.get("sections", {}).get(
        "H_authorization_boundary", {}
    ).get("decision_status", "BLOCKED")
    candidate_root = paths.prospective_candidate_shadow
    signal_ledgers = sorted(candidate_root.rglob("PROSPECTIVE_SIGNAL_LEDGER.ndjson"))
    outcome_ledgers = sorted(candidate_root.rglob("PROSPECTIVE_OUTCOME_LEDGER.ndjson"))
    signals = [row for path in signal_ledgers for row in read_ndjson(path)]
    outcomes = [row for path in outcome_ledgers for row in read_ndjson(path)]
    settled_candidates = {str(row["candidate_id"]) for row in outcomes}
    pending_signals = [
        row
        for row in signals
        if row.get("candidate_status") == "FROZEN"
        and str(row["candidate_id"]) not in settled_candidates
    ]
    latest_candidate_path = _latest_file(candidate_root, "CANDIDATE_SIGNAL.json")
    latest_execution_path = _latest_file(candidate_root, "EXECUTION_QUOTE.json")
    latest_candidate = _load_json(latest_candidate_path) or {}
    latest_execution = _load_json(latest_execution_path) or {}
    registry = ModelDispositionRegistry.load()
    return {
        "schema_version": "mso-private-operator-state-v2",
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "scheduler": _scheduler_status(),
        "runtime": runtime_status,
        "runtime_process": process_state,
        "current_quality": quality or None,
        "current_quality_path": str(quality_path) if quality_path else None,
        "latest_completed_run_date": quality.get("trading_date"),
        "latest_completed_run_id": quality.get("run_id"),
        "latest_report": report or None,
        "latest_report_path": str(report_path) if report_path else None,
        "latest_incidents": _load_json(incident_path),
        "capture_pipeline_status": "PASS" if capture_pipeline_pass else "FAIL",
        "decision_point_feed_status": "PASS" if decision_feed_pass else "FAIL",
        "decision_status": "PASS" if decision_status == "MODEL_SHADOW_ONLY" else "BLOCKED",
        "decision_status_detail": decision_status,
        "candidate_authorization": {
            "label": "CANDIDATE ONLY",
            "detail": "Not calibrated or validated",
        },
        "prospective_candidate_authorization": {
            "label": "PROSPECTIVE CANDIDATE",
            "detail": "Counterfactual only; not calibrated, validated, or a recommendation",
        },
        "candidate_shadow": {
            "latest_signal": latest_candidate or None,
            "latest_signal_path": str(latest_candidate_path) if latest_candidate_path else None,
            "latest_execution_quote": latest_execution or None,
            "latest_execution_quote_path": str(latest_execution_path) if latest_execution_path else None,
            "signal_records": len(signals),
            "pending_signal_records": len(pending_signals),
            "settled_outcome_records": len(outcomes),
            "gate_status": distinct_date_gate_status(signals),
            "accuracy": summarize_outcomes(outcomes),
            "labels": [
                "PROSPECTIVE CANDIDATE",
                "OUTCOME PENDING" if pending_signals else "NO OUTCOME PENDING",
                "SETTLED" if outcomes else "INSUFFICIENT",
                "MODEL SHADOW DISABLED",
            ],
        },
        "model_disposition_registry": registry.payload,
        "model_disposition_sha256": registry.sha256,
        "soak_progress": {
            "qualifying_pass": sum(
                bool(row.get("data_quality_pass")) for row in rehearsal_quality
            ),
            "qualifying_required": 3,
            "total_rehearsal_runs": len(rehearsal_runs),
            "formal_valid_days": sum(bool(row.get("counts_toward_20_day_gate")) for row in formal_quality),
            "formal_required_days": 20,
        },
        "model_shadow_status": "DISABLED_NOT_AUTHORIZED",
        "alerts": load_recent_alerts(paths.alerts),
        "logs": [str(path) for path in sorted(paths.logs.glob("*"), reverse=True)[:25]],
        "private_lineage": [
            str(path)
            for path in sorted(
                [*paths.label_ledger.rglob("*.json"), *candidate_root.rglob("*.json")],
                reverse=True,
            )[:25]
        ],
        "paper_positions": 0,
        "real_orders": 0,
    }


def rerun_quality(paths: RuntimePaths) -> Path:
    run_path = _latest_file(paths.data_shadow, "RUN.json")
    if run_path is None:
        raise FileNotFoundError("No formal data-shadow run is available")
    release_root = Path(os.environ["MSO_RELEASE_ROOT"])
    universe = json.loads(
        (release_root / "frozen" / "runtime_universe_v1.json").read_text(encoding="utf-8")
    )
    quality = evaluate_run_quality(run_path.parent, universe)
    quality["recheck_id"] = str(uuid.uuid4())
    quality["rechecked_at_utc"] = datetime.now(UTC).isoformat()
    output = run_path.parent / "quality" / f"QUALITY_RECHECK-{quality['recheck_id']}.json"
    write_exclusive(output, canonical_json(quality))
    return output


def retry_publication(paths: RuntimePaths) -> str:
    quality = _latest_file(paths.data_shadow, "DATA_QUALITY.json")
    if quality is None:
        raise FileNotFoundError("No formal data-shadow quality artifact is available")
    runtime_config = _load_json(paths.root / "runtime_paths.json") or {}
    repository = runtime_config.get("repository_root")
    if not repository:
        raise ValueError("Runtime repository path is unavailable")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "market_state_observatory.publication.runtime_publisher",
            "--repository",
            str(repository),
            "--quality",
            str(quality),
            "--push",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode:
        raise ValueError("Fail-closed publication retry was rejected")
    return "PUBLICATION_RETRY_COMPLETE"


HTML = """<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>MSO Private Operator</title>
<style>:root{color-scheme:light;--ink:#13221d;--muted:#607069;--line:#d9e1dd;--paper:#f7f9f8;--accent:#1e6650;--bad:#9d2f2f;--warn:#8a5b05}*{box-sizing:border-box}body{margin:0;font:14px system-ui;color:var(--ink);background:#fff}header{position:sticky;top:0;background:#fff;border-bottom:1px solid var(--line);padding:14px 22px;display:flex;align-items:center;justify-content:space-between;gap:12px;z-index:3}header h1{font-size:17px;margin:0}nav{display:flex;gap:4px;padding:10px 20px;border-bottom:1px solid var(--line)}nav button{white-space:nowrap;border:0;background:transparent;padding:8px 10px;color:var(--muted)}nav button[aria-pressed=true]{color:var(--accent);border-bottom:2px solid var(--accent)}main{max-width:1220px;margin:auto;padding:24px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.card{min-width:0;border:1px solid var(--line);padding:14px;background:#fff}.card h2{font-size:13px;color:var(--muted);margin:0 0 10px}.value{font-size:21px;font-weight:650;overflow-wrap:anywhere}.badge{display:inline-block;font-size:11px;font-weight:700;border:1px solid currentColor;padding:3px 6px;margin:2px 4px 2px 0}.observed,.pass{color:#245f4c}.candidate{color:#705400}.blocked,.fail{color:var(--bad)}.disabled{color:#68736e}.themes{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:18px}.matrix-wrap{overflow:auto;margin-top:18px;border:1px solid var(--line)}table{width:100%;border-collapse:collapse;min-width:780px}th,td{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid var(--line)}th{font-size:12px;color:var(--muted);background:var(--paper)}pre{background:var(--paper);padding:14px;overflow:auto;border:1px solid var(--line);max-height:60vh}.toolbar{display:flex;gap:8px;margin:14px 0}.toolbar button{padding:8px 11px;border:1px solid var(--line);background:#fff}.reason{color:var(--bad);font-weight:650}.skip{position:absolute;left:-9999px}.skip:focus{left:10px;top:10px;background:#fff;padding:8px;z-index:10}.mobile-more{display:none}.more-menu{display:none;position:absolute;right:12px;top:112px;z-index:4;border:1px solid var(--line);background:#fff;padding:6px;box-shadow:0 8px 24px #0002}.more-menu button{display:block;width:100%;text-align:left;border:0;background:#fff;padding:10px}.more-menu.open{display:block}@media(max-width:760px){header{align-items:flex-start}.grid,.themes{grid-template-columns:1fr 1fr}main{padding:16px}nav{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));padding:8px 10px;overflow:visible}nav button{padding:9px 4px}.secondary-nav{display:none}.mobile-more{display:block}}@media(max-width:460px){.grid,.themes{grid-template-columns:1fr}}</style></head><body>
<a class='skip' href='#content'>Skip to content</a><header><h1>Market State Observatory <span class='badge candidate'>PRIVATE OPERATOR</span></h1><span class='private'>127.0.0.1 only</span></header>
<nav aria-label='Operator pages' id='nav'></nav><div id='more-menu' class='more-menu' aria-label='More operator pages'></div><main id='content' tabindex='-1'><div id='loading' role='status'>Loading private evidence</div><div id='app' hidden></div></main>
<script>
const pages=['Today','Yesterday','Themes','Candidate Shadow','Pending Outcomes','Settled Outcomes','Accuracy','Timing','Model Graveyard','Observation Report','State Certificates','Evidence','Incidents','Experiments','Promotion Gates','Settings'];const primaryPages=new Set(['Today','Yesterday','Themes']);let state;
function esc(v){return String(v??'not available').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function badge(label,kind='disabled'){return `<span class="badge ${kind}">${esc(label)}</span>`}
function card(title,value,detail=''){const kind=value==='PASS'?'pass':value==='FAIL'||value==='BLOCKED'?'fail':'';return `<article class="card"><h2>${esc(title)}</h2><div class="value ${kind}">${esc(value)}</div>${detail?`<p>${esc(detail)}</p>`:''}</article>`}
function pct(v){return v==null?'n/a':(Number(v)*100).toFixed(2)+'%'}
function candidateEstimated(t){const d=t.candidate_outputs?.direction||[];return d.some(x=>x.candidate_estimated===true)||t.candidate_outputs?.transmission?.candidate_estimated===true}
function themes(){const rows=state.latest_report?.sections?.C_descriptive_theme_structure?.themes||[];return `<div class="themes">${rows.map(t=>{const estimated=candidateEstimated(t);const conflicts=t.descriptive_structure_conflicts||[];return `<article class="card"><h2>${esc(t.display_name)} · ${esc(t.theme_etf)}</h2>${badge('OBSERVED','observed')} ${badge(estimated?'CANDIDATE':'CANDIDATE NOT ESTIMATED',estimated?'candidate':'disabled')} ${t.data_incident_exposure?.decision_quote_stale?badge('DATA_BLOCKED','blocked'):''}${conflicts.map(x=>badge('DESCRIPTIVE: '+x.conflict_type,'candidate')).join('')}<p>${esc((t.descriptive_findings||[]).join(' '))}</p></article>`}).join('')}</div>`}
function matrix(){const rows=state.latest_report?.sections?.C_descriptive_theme_structure?.themes||[];return `<div class="matrix-wrap" tabindex="0" aria-label="Six-theme structure matrix"><table><thead><tr><th>Theme</th><th>ETF vs SPY</th><th>Breadth</th><th>ETF / basket</th><th>Dispersion</th><th>Late state</th></tr></thead><tbody>${rows.map(t=>{const path=t.etf_path||[],last=path[path.length-1]||{},c=t.close_structure||{},agreement=c.etf_basket_agreement;return `<tr><td>${esc(t.display_name)}</td><td>${pct(last.relative_to_spy)}</td><td>${pct(c.constituent_positive_breadth)}</td><td>${agreement==null?'n/a':agreement?'ALIGNED':'DISAGREEMENT'}</td><td>${pct(c.return_dispersion)}</td><td>${esc((t.descriptive_findings||[]).join(' '))}</td></tr>`}).join('')}</tbody></table></div>`}
function render(page){document.querySelectorAll('nav button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.page===page)));const q=state.current_quality||{},r=state.latest_report||{},inc=state.latest_incidents||{},s=state.soak_progress;let html='';
if(page==='Today')html=`<h2>Latest completed evidence</h2><p class="reason">${esc(r.headline||'NO COMPLETED REPORT')}</p><div class="grid">${card('Capture pipeline',state.capture_pipeline_status)}${card('Decision-point feed',state.decision_point_feed_status)}${card('Decision status',state.decision_status,state.decision_status_detail)}${card('Qualifying soak PASS',s.qualifying_pass+'/'+s.qualifying_required)}${card('Total rehearsal runs',s.total_rehearsal_runs)}${card('Formal',s.formal_valid_days+'/'+s.formal_required_days)}${card('Positions / orders','0 / 0')}${card('Candidate authorization',state.candidate_authorization.label,state.candidate_authorization.detail)}</div>${matrix()}${themes()}`;
else if(page==='Themes')html=`<h2>Six-theme descriptive structure</h2>${matrix()}${themes()}`;
else if(page==='Candidate Shadow'){const c=state.candidate_shadow||{};html=`<h2>Prospective Candidate Shadow</h2>${badge('PROSPECTIVE CANDIDATE','candidate')}${badge('NOT A RECOMMENDATION','disabled')}${badge('MODEL SHADOW DISABLED','disabled')}<div class="grid">${card('Signal records',c.signal_records||0)}${card('Pending signals',c.pending_signal_records||0)}${card('Settled outcomes',c.settled_outcome_records||0)}${card('Positions / orders','0 / 0')}</div><pre>${esc(JSON.stringify(c.latest_signal||{status:'INSUFFICIENT'},null,2))}</pre>`}
else if(page==='Pending Outcomes'){const c=state.candidate_shadow||{};html=`<h2>Pending Outcomes</h2>${badge(c.pending_signal_records?'OUTCOME PENDING':'INSUFFICIENT',c.pending_signal_records?'candidate':'disabled')}<pre>${esc(JSON.stringify({pending_signal_records:c.pending_signal_records,gate_status:c.gate_status},null,2))}</pre>`}
else if(page==='Settled Outcomes'){const c=state.candidate_shadow||{};html=`<h2>Settled Outcomes</h2>${badge(c.settled_outcome_records?'SETTLED':'INSUFFICIENT',c.settled_outcome_records?'observed':'disabled')}<pre>${esc(JSON.stringify({settled_outcome_records:c.settled_outcome_records,latest_execution_quote:c.latest_execution_quote},null,2))}</pre>`}
else if(page==='Accuracy'){const c=state.candidate_shadow||{};html=`<h2>Candidate Accuracy</h2>${badge((c.accuracy||[]).length?'PROSPECTIVE CANDIDATE':'INSUFFICIENT',(c.accuracy||[]).length?'candidate':'disabled')}<p>Metrics use settled common legal dates only. They do not authorize a model.</p><pre>${esc(JSON.stringify(c.accuracy||[],null,2))}</pre>`}
else if(page==='Timing'){const c=state.candidate_shadow||{},signal=c.latest_signal||{},quote=c.latest_execution_quote||{};html=`<h2>Timing Evidence</h2><div class="grid">${card('Candidate generated',signal.generated_at_utc||'INSUFFICIENT')}${card('Execution quote observed',quote.captured_at_utc||'INSUFFICIENT')}${card('Candidate status',signal.candidate_status||'INSUFFICIENT')}${card('Quote status',quote.status||'INSUFFICIENT')}</div>`}
else if(page==='Model Graveyard'){const m=state.model_disposition_registry?.models||{};html=`<h2>Model Graveyard</h2>${badge('RETIRED','disabled')}${badge('DESCRIPTIVE','observed')}${badge('MODEL SHADOW DISABLED','disabled')}<div class="matrix-wrap"><table><thead><tr><th>Model</th><th>Disposition</th><th>Production activation</th></tr></thead><tbody>${Object.entries(m).map(([id,row])=>`<tr><td>${esc(id)}</td><td>${esc(row.disposition)}</td><td>${row.production_activation_allowed?'ALLOWED':'BLOCKED'}</td></tr>`).join('')}</tbody></table></div>`}
else if(page==='Observation Report')html=`<h2>Observation Report</h2>${badge(r.evidence_grade||'NOT AVAILABLE','observed')}<pre>${esc(JSON.stringify(r,null,2))}</pre>`;
else if(page==='State Certificates')html=`<h2>Candidate certificates</h2><p>All certificates remain retrospective, unvalidated, and decision ineligible.</p>${themes()}`;
else if(page==='Incidents')html=`<h2>Connection and freshness incidents</h2><pre>${esc(JSON.stringify(inc,null,2))}</pre>`;
else if(page==='Experiments')html=`<h2>Experiment registry</h2>${badge('DESCRIPTIVE','observed')}${badge('RETIRED','disabled')}${badge('PROSPECTIVE CANDIDATE','candidate')}${badge('NOT CALIBRATED','candidate')}${badge('MODEL_SHADOW_ONLY','disabled')}${badge('MODEL SHADOW DISABLED','disabled')}${badge('DISABLED','disabled')}<p>Rehearsal dates are excluded from official strategy evidence. Candidate output is not a recommendation.</p>`;
else if(page==='Promotion Gates')html=`<h2>Authorization gates</h2><div class="grid">${card('Qualifying soak',s.qualifying_pass+'/'+s.qualifying_required)}${card('Formal Data Shadow',s.formal_valid_days+'/'+s.formal_required_days)}${card('Model Shadow',state.model_shadow_status)}${card('Paper / live','UNAVAILABLE')}${card('Positions / orders','0 / 0')}</div>`;
else if(page==='Settings')html=`<h2>Private settings and controls</h2><div class="toolbar"><button onclick="act('/api/retry-quality')">Re-run quality</button><button onclick="act('/api/retry-publication')">Retry eligible publication</button><button onclick="load()">Refresh</button></div><pre>${esc(JSON.stringify({scheduler:state.scheduler,runtime_process:state.runtime_process,current_quality_path:state.current_quality_path,latest_report_path:state.latest_report_path},null,2))}</pre>`;
else html=`<h2>${esc(page)}</h2><pre>${esc(JSON.stringify(page==='Evidence'?{quality:q,report_path:state.latest_report_path}:state,null,2))}</pre>`;
document.querySelector('#app').innerHTML=html;document.querySelector('#more-menu').classList.remove('open')}
async function load(){const response=await fetch('/api/status');state=await response.json();document.querySelector('#loading').hidden=true;document.querySelector('#app').hidden=false;render(decodeURIComponent(location.hash.slice(1))||'Today')}
async function act(path){const response=await fetch(path,{method:'POST'});const value=await response.json();alert(value.status||value.reason||'complete');await load()}
function go(page){location.hash=page;render(page)}const nav=document.querySelector('#nav'),more=document.querySelector('#more-menu');pages.forEach(page=>{const b=document.createElement('button');b.textContent=page;b.dataset.page=page;b.onclick=()=>go(page);b.setAttribute('aria-pressed','false');if(!primaryPages.has(page))b.className='secondary-nav';nav.appendChild(b);if(!primaryPages.has(page)){const m=b.cloneNode(true);m.className='';m.onclick=()=>go(page);more.appendChild(m)}});const moreButton=document.createElement('button');moreButton.textContent='More';moreButton.className='mobile-more';moreButton.setAttribute('aria-expanded','false');moreButton.onclick=()=>{const open=more.classList.toggle('open');moreButton.setAttribute('aria-expanded',String(open))};nav.appendChild(moreButton);addEventListener('hashchange',()=>state&&render(decodeURIComponent(location.hash.slice(1))||'Today'));load();
</script></body></html>"""


def make_handler(paths: RuntimePaths) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, sort_keys=True).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                body = HTML.encode()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/api/status":
                self._json(operator_state(paths))
            else:
                self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            try:
                if self.path == "/api/retry-quality":
                    self._json({"status": "CREATED", "path": str(rerun_quality(paths))})
                elif self.path == "/api/retry-publication":
                    self._json({"status": retry_publication(paths)})
                else:
                    self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            except (FileNotFoundError, KeyError, ValueError) as exc:
                self._json({"status": "BLOCKED", "reason": str(exc)}, HTTPStatus.CONFLICT)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def serve(paths: RuntimePaths, host: str = HOST, port: int = 8765) -> None:
    if host != HOST:
        raise ValueError("Private operator console must bind to 127.0.0.1")
    server = ThreadingHTTPServer((host, port), make_handler(paths))
    print(f"OPERATOR_CONSOLE=http://{host}:{port}")
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    serve(resolve_runtime_paths(create=True), args.host, args.port)


if __name__ == "__main__":
    main()

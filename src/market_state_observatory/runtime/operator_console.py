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

from .notifications import load_recent_alerts
from .observation_freezer import canonical_json, write_exclusive
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
    result = subprocess.run(
        ["schtasks.exe", "/Query", "/TN", "MSO-Daily-Runtime", "/FO", "LIST"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return {"state": "INSTALLED" if result.returncode == 0 else "NOT_INSTALLED"}


def operator_state(paths: RuntimePaths) -> dict[str, Any]:
    runtime_status = _load_json(_latest_file(paths.operator, "runtime-status*.json")) or {}
    quality_path = _latest_file(paths.data_shadow, "DATA_QUALITY.json")
    return {
        "schema_version": "mso-private-operator-state-v1",
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "scheduler": _scheduler_status(),
        "runtime": runtime_status,
        "current_quality": _load_json(quality_path),
        "current_quality_path": str(quality_path) if quality_path else None,
        "alerts": load_recent_alerts(paths.alerts),
        "logs": [str(path) for path in sorted(paths.logs.glob("*"), reverse=True)[:25]],
        "private_lineage": [
            str(path) for path in sorted(paths.label_ledger.rglob("*.json"), reverse=True)[:25]
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


HTML = """<!doctype html><html><head><meta charset='utf-8'><title>MSO Operator</title>
<style>body{font:14px system-ui;margin:24px;max-width:1200px;color:#17202a}button{margin-right:8px;padding:8px 12px}
pre{background:#f4f6f7;padding:16px;overflow:auto;border:1px solid #ccd1d1}</style></head><body>
<h1>Private Operator Console</h1><p>Localhost only. Private runtime state is never published.</p>
<button onclick="act('/api/retry-quality')">Re-run quality</button><button onclick="act('/api/retry-publication')">Retry publication</button><button onclick="load()">Refresh</button>
<pre id='state'>Loading</pre><script>async function load(){const r=await fetch('/api/status');
document.querySelector('#state').textContent=JSON.stringify(await r.json(),null,2)}
async function act(p){const r=await fetch(p,{method:'POST'});alert(JSON.stringify(await r.json()));load()}load()</script>
</body></html>"""


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

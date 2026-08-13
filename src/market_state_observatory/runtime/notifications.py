from __future__ import annotations

import argparse
import base64
import contextlib
import json
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

from ..security import assert_credential_values_absent
from .observation_freezer import canonical_json, write_exclusive

ALERT_KINDS = {
    "task_not_started",
    "credential_invalid",
    "websocket_disconnected",
    "observation_missed",
    "quality_failed",
    "publication_failed",
    "public_site_stale",
}


def _toast_script(title: str, body: str) -> str:
    title64 = base64.b64encode(title.encode()).decode()
    body64 = base64.b64encode(body.encode()).decode()
    return f"""
$title=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{title64}'))
$body=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{body64}'))
[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime] > $null
$xml=New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml('<toast><visual><binding template="ToastGeneric"><text></text><text></text></binding></visual></toast>')
$nodes=$xml.GetElementsByTagName('text'); $nodes.Item(0).AppendChild($xml.CreateTextNode($title)) > $null
$nodes.Item(1).AppendChild($xml.CreateTextNode($body)) > $null
$toast=New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Market State Observatory').Show($toast)
"""


def emit_local_alert(
    alerts_directory: Path,
    *,
    kind: str,
    title: str,
    message: str,
    run_id: str | None = None,
    toast: bool = True,
) -> Path:
    if kind not in ALERT_KINDS:
        raise ValueError(f"Unsupported alert kind: {kind}")
    payload = {
        "schema_version": "mso-private-alert-v1",
        "alert_id": str(uuid.uuid4()),
        "kind": kind,
        "title": title,
        "message": message,
        "run_id": run_id,
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "delivery": "windows_toast_best_effort" if toast else "private_ledger_only",
        "paper_positions": 0,
        "real_orders": 0,
    }
    encoded = canonical_json(payload)
    assert_credential_values_absent(encoded)
    observed = str(payload["observed_at_utc"]).replace(":", "")
    path = alerts_directory / f"{observed}-{payload['alert_id']}.json"
    write_exclusive(path, encoded)
    if toast:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _toast_script(title, message)],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
    return path


def load_recent_alerts(alerts_directory: Path, limit: int = 50) -> list[dict[str, object]]:
    paths = sorted(alerts_directory.glob("*.json"), reverse=True)[:limit]
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=sorted(ALERT_KINDS), required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--no-toast", action="store_true")
    args = parser.parse_args()
    from .runtime_paths import resolve_runtime_paths

    path = emit_local_alert(
        resolve_runtime_paths(create=True).alerts,
        kind=args.kind,
        title=args.title,
        message=args.message,
        run_id=args.run_id,
        toast=not args.no_toast,
    )
    print(f"ALERT_RECORDED={path.name}")


if __name__ == "__main__":
    main()

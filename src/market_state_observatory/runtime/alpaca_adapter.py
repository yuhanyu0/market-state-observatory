from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, time
from email.utils import parsedate_to_datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests
import websockets

from ..security import assert_credential_values_absent, scan_text
from .credential_loader import require_child_process_credentials

DATA_ENDPOINT = "https://data.alpaca.markets/v2"
STREAM_ENDPOINT = "wss://stream.data.alpaca.markets/v2/sip"
PROVIDER = "Alpaca Market Data SIP"
PARSER_VERSION = "mso-alpaca-sip-parser-v1"
INGESTION_VERSION = "mso-runtime-ingestion-v1"
ET = ZoneInfo("America/New_York")


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class RestResult:
    collector_request_id: str
    provider_request_id: str | None
    request_started_at_utc: str
    observed_at_utc: str
    response_status: int
    sanitized_request_parameters: dict[str, Any]
    response_headers_sha256: str
    raw_response: bytes
    body: dict[str, Any]
    server_date_utc: str | None

    def metadata(self) -> dict[str, Any]:
        return {
            "collector_request_id": self.collector_request_id,
            "provider_request_id": self.provider_request_id,
            "request_started_at_utc": self.request_started_at_utc,
            "observed_at_utc": self.observed_at_utc,
            "response_status": self.response_status,
            "sanitized_request_parameters": self.sanitized_request_parameters,
            "response_headers_sha256": self.response_headers_sha256,
            "provider": PROVIDER,
            "parser_version": PARSER_VERSION,
            "ingestion_version": INGESTION_VERSION,
            "feed": "sip",
        }


@dataclass(frozen=True)
class SymbolCapture:
    symbol: str
    quote: dict[str, Any]
    last_trade: dict[str, Any]
    minute_bar: dict[str, Any]
    vwap: float | None
    cumulative_volume: float
    included_interval_start_utc: str | None
    included_interval_end_utc: str | None
    quote_age_seconds: float


@dataclass(frozen=True)
class PointCapture:
    observation_point: str
    scheduled_at_utc: str
    captured_at_utc: str
    symbols: tuple[SymbolCapture, ...]
    raw_results: tuple[RestResult, ...]


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ProviderError("Timestamp must include timezone")
    return parsed.astimezone(UTC)


def _safe_failure(kind: str, request_id: str) -> ProviderError:
    return ProviderError(f"Alpaca SIP {kind}; collector_request_id={request_id}")


class AlpacaSIPAdapter:
    def __init__(self, timeout_seconds: float = 20.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.reconnect_count = 0

    @staticmethod
    def readiness() -> dict[str, Any]:
        try:
            require_child_process_credentials()
            available = True
        except RuntimeError:
            available = False
        return {
            "provider": PROVIDER,
            "credential_status": "PRESENT" if available else "ABSENT",
            "feed": "sip",
            "rest_endpoint": DATA_ENDPOINT,
            "websocket_endpoint": STREAM_ENDPOINT,
            "silent_iex_fallback": False,
        }

    def _get(self, path: str, parameters: dict[str, Any] | None = None) -> RestResult:
        request_id = str(uuid.uuid4())
        started = datetime.now(UTC)
        params = dict(parameters or {})
        if params.get("feed") not in (None, "sip"):
            raise ProviderError("Non-SIP market data feed rejected")
        params["feed"] = "sip"
        key_id, secret = require_child_process_credentials()
        headers = {
            "APCA-API-KEY-ID": key_id,
            "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json",
            "X-Collector-Request-ID": request_id,
        }
        try:
            response = self.session.get(
                f"{DATA_ENDPOINT}{path}",
                params=params,
                headers=headers,
                timeout=self.timeout_seconds,
            )
            observed = datetime.now(UTC)
            raw = response.content
            assert_credential_values_absent(raw)
            if scan_text(raw.decode("utf-8", errors="replace"), request_id):
                raise _safe_failure("response rejected by safety scanner", request_id)
            if response.status_code >= 400:
                raise _safe_failure(f"HTTP {response.status_code}", request_id)
            safe_headers = {
                str(name).lower(): str(value)
                for name, value in response.headers.items()
                if name.lower() not in {"authorization", "set-cookie", "cookie"}
            }
            header_hash = hashlib.sha256(
                json.dumps(safe_headers, sort_keys=True).encode()
            ).hexdigest()
            server_date = response.headers.get("Date")
            server_date_utc = (
                parsedate_to_datetime(server_date).astimezone(UTC).isoformat()
                if server_date
                else None
            )
            return RestResult(
                collector_request_id=request_id,
                provider_request_id=response.headers.get("X-Request-ID"),
                request_started_at_utc=started.isoformat(),
                observed_at_utc=observed.isoformat(),
                response_status=response.status_code,
                sanitized_request_parameters=params,
                response_headers_sha256=header_hash,
                raw_response=raw,
                body=response.json(),
                server_date_utc=server_date_utc,
            )
        except ProviderError:
            raise
        except Exception as error:
            raise _safe_failure(type(error).__name__, request_id) from None

    def snapshots(self, symbols: Iterable[str]) -> RestResult:
        return self._get("/stocks/snapshots", {"symbols": ",".join(sorted(set(symbols)))})

    def latest_quotes(self, symbols: Iterable[str]) -> RestResult:
        return self._get("/stocks/quotes/latest", {"symbols": ",".join(sorted(set(symbols)))})

    def latest_trades(self, symbols: Iterable[str]) -> RestResult:
        return self._get("/stocks/trades/latest", {"symbols": ",".join(sorted(set(symbols)))})

    def minute_bars(
        self,
        symbols: Iterable[str],
        start_utc: datetime,
        end_utc: datetime,
        page_token: str | None = None,
    ) -> RestResult:
        parameters: dict[str, Any] = {
            "symbols": ",".join(sorted(set(symbols))),
            "timeframe": "1Min",
            "start": start_utc.astimezone(UTC).isoformat(),
            "end": end_utc.astimezone(UTC).isoformat(),
            "limit": 10000,
            "adjustment": "raw",
            "sort": "asc",
        }
        if page_token:
            parameters["page_token"] = page_token
        return self._get("/stocks/bars", parameters)

    @staticmethod
    def validate_capture_window(scheduled_at: datetime, invoked_at: datetime) -> None:
        scheduled = scheduled_at.astimezone(UTC)
        invoked = invoked_at.astimezone(UTC)
        if invoked < scheduled:
            raise ProviderError("Observation point is not due")
        if (invoked - scheduled).total_seconds() > 60:
            raise ProviderError("missed_observation: invocation exceeded 60-second tolerance")

    def _all_bars(
        self,
        symbols: list[str],
        start_utc: datetime,
        end_utc: datetime,
    ) -> tuple[dict[str, list[dict[str, Any]]], list[RestResult]]:
        grouped: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in symbols}
        results: list[RestResult] = []
        for offset in range(0, len(symbols), 20):
            chunk = symbols[offset : offset + 20]
            page_token: str | None = None
            while True:
                result = self.minute_bars(chunk, start_utc, end_utc, page_token)
                results.append(result)
                for symbol, rows in result.body.get("bars", {}).items():
                    grouped.setdefault(symbol, []).extend(rows)
                page_token = result.body.get("next_page_token")
                if not page_token:
                    break
        return grouped, results

    def capture_exact_point(
        self,
        symbols: Iterable[str],
        observation_point: str,
        scheduled_at: datetime,
        invoked_at: datetime | None = None,
    ) -> PointCapture:
        invoked = invoked_at or datetime.now(UTC)
        self.validate_capture_window(scheduled_at, invoked)
        symbol_list = sorted(set(symbols))
        quote_result = self.latest_quotes(symbol_list)
        trade_result = self.latest_trades(symbol_list)
        snapshot_result = self.snapshots(symbol_list)
        market_open = datetime.combine(scheduled_at.astimezone(ET).date(), time(9, 30), ET)
        bars_by_symbol, bar_results = self._all_bars(
            symbol_list, market_open.astimezone(UTC), scheduled_at.astimezone(UTC)
        )
        quotes = quote_result.body.get("quotes", {})
        trades = trade_result.body.get("trades", {})
        captures: list[SymbolCapture] = []
        for symbol in symbol_list:
            quote = quotes.get(symbol)
            trade = trades.get(symbol)
            bars = [
                bar
                for bar in bars_by_symbol.get(symbol, [])
                if parse_utc(str(bar["t"])) <= scheduled_at.astimezone(UTC)
            ]
            if not quote or not trade or not bars:
                continue
            observed = parse_utc(quote_result.observed_at_utc)
            quote_time = parse_utc(str(quote["t"]))
            quote_age = (observed - quote_time).total_seconds()
            bid = float(quote["bp"])
            ask = float(quote["ap"])
            mid = (bid + ask) / 2
            if quote_time > observed or not 0 <= quote_age <= 60:
                continue
            if bid <= 0 or ask <= 0 or ask < bid or not bid <= mid <= ask:
                continue
            legal_bars = sorted(bars, key=lambda item: str(item["t"]))
            volume = sum(float(item.get("v", 0)) for item in legal_bars)
            numerator = sum(
                float(item.get("vw", item["c"])) * float(item.get("v", 0))
                for item in legal_bars
            )
            latest = legal_bars[-1]
            captures.append(
                SymbolCapture(
                    symbol=symbol,
                    quote={
                        "bid": bid,
                        "ask": ask,
                        "mid": mid,
                        "quoted_spread": ask - bid,
                        "event_time_utc": quote_time.isoformat(),
                    },
                    last_trade={
                        "price": float(trade["p"]),
                        "event_time_utc": parse_utc(str(trade["t"])).isoformat(),
                    },
                    minute_bar={
                        "open": float(latest["o"]),
                        "high": float(latest["h"]),
                        "low": float(latest["l"]),
                        "close": float(latest["c"]),
                        "volume": float(latest["v"]),
                        "event_time_utc": parse_utc(str(latest["t"])).isoformat(),
                    },
                    vwap=numerator / volume if volume > 0 else None,
                    cumulative_volume=volume,
                    included_interval_start_utc=parse_utc(str(legal_bars[0]["t"])).isoformat(),
                    included_interval_end_utc=parse_utc(str(latest["t"])).isoformat(),
                    quote_age_seconds=quote_age,
                )
            )
        return PointCapture(
            observation_point=observation_point,
            scheduled_at_utc=scheduled_at.astimezone(UTC).isoformat(),
            captured_at_utc=datetime.now(UTC).isoformat(),
            symbols=tuple(captures),
            raw_results=(quote_result, trade_result, snapshot_result, *bar_results),
        )

    def clock_skew_seconds(self) -> float | None:
        result = self.latest_quotes(["SPY"])
        if not result.server_date_utc:
            return None
        return abs((parse_utc(result.observed_at_utc) - parse_utc(result.server_date_utc)).total_seconds())

    async def stream(
        self,
        symbols: Iterable[str],
        on_message: Callable[[dict[str, Any], bytes], Awaitable[None]],
        stop: asyncio.Event,
    ) -> None:
        key_id, secret = require_child_process_credentials()
        symbol_list = sorted(set(symbols))
        delay = 1.0
        while not stop.is_set():
            try:
                async with websockets.connect(STREAM_ENDPOINT) as websocket:
                    await websocket.send(json.dumps({"action": "auth", "key": key_id, "secret": secret}))
                    auth_raw = await websocket.recv()
                    auth = json.loads(auth_raw)
                    if not any(row.get("T") == "success" for row in auth):
                        raise ProviderError("Alpaca SIP WebSocket authentication failed")
                    await websocket.send(
                        json.dumps(
                            {
                                "action": "subscribe",
                                "quotes": symbol_list,
                                "trades": symbol_list,
                                "bars": symbol_list,
                            }
                        )
                    )
                    delay = 1.0
                    while not stop.is_set():
                        raw = await asyncio.wait_for(websocket.recv(), timeout=30)
                        raw_bytes = raw.encode() if isinstance(raw, str) else bytes(raw)
                        assert_credential_values_absent(raw_bytes)
                        if scan_text(raw_bytes.decode("utf-8", errors="replace"), "websocket"):
                            raise ProviderError("WebSocket payload rejected by safety scanner")
                        for item in json.loads(raw_bytes):
                            if item.get("T") in {"q", "t", "b"}:
                                await on_message(item, raw_bytes)
            except TimeoutError:
                continue
            except Exception as error:
                if stop.is_set():
                    return
                self.reconnect_count += 1
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60.0)
                if isinstance(error, ProviderError) and "authentication" in str(error):
                    raise

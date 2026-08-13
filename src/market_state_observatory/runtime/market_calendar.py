from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from typing import Any, cast
from zoneinfo import ZoneInfo

import exchange_calendars as exchange_calendars  # type: ignore[import-untyped]

ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class SessionSchedule:
    trading_date: date
    market_open: datetime
    midpoint: datetime
    close_minus_30m: datetime
    close_minus_15m: datetime
    market_close: datetime

    def observation_points(self) -> tuple[tuple[str, datetime], ...]:
        points = (
            ("open_snapshot", self.market_open),
            ("midpoint_snapshot", self.midpoint),
            ("preclose_snapshot", self.close_minus_30m),
            ("decision_snapshot", self.close_minus_15m),
            ("session_close_diagnostic", self.market_close),
        )
        return tuple(sorted(points, key=lambda row: row[1]))


@lru_cache(maxsize=1)
def _xnys() -> Any:
    return exchange_calendars.get_calendar("XNYS")


def _session_label(day: date) -> str:
    return day.isoformat()


def is_trading_day(day: date) -> bool:
    return bool(_xnys().is_session(_session_label(day)))


def next_trading_day(day: date) -> date:
    label = _xnys().date_to_session(_session_label(day), direction="next")
    candidate = cast(date, label.date())
    if candidate == day:
        label = _xnys().next_session(label)
    return cast(date, label.date())


def session_schedule(day: date) -> SessionSchedule:
    calendar = _xnys()
    label = _session_label(day)
    if not calendar.is_session(label):
        raise ValueError(f"Not an XNYS trading session: {day.isoformat()}")
    market_open = calendar.session_open(label).to_pydatetime().astimezone(ET)
    market_close = calendar.session_close(label).to_pydatetime().astimezone(ET)
    duration = market_close - market_open
    return SessionSchedule(
        trading_date=day,
        market_open=market_open,
        midpoint=market_open + duration / 2,
        close_minus_30m=market_close - timedelta(minutes=30),
        close_minus_15m=market_close - timedelta(minutes=15),
        market_close=market_close,
    )


def market_close_time(day: date) -> tuple[int, int]:
    close = session_schedule(day).market_close
    return close.hour, close.minute


def schedule_as_utc(day: date) -> tuple[tuple[str, datetime], ...]:
    return tuple(
        (name, timestamp.astimezone(UTC))
        for name, timestamp in session_schedule(day).observation_points()
    )


def now_et() -> datetime:
    return datetime.now(ET)

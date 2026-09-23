"""Configurable market-session calculations for dashboard data refreshes."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[4] / "config" / "market_hours.json"
DEFAULT_CONFIG: dict[str, Any] = {
    "market": "US equities",
    "timezone": "America/New_York",
    "weekdays": [0, 1, 2, 3, 4],
    "open_time": "09:30",
    "close_time": "16:00",
    "refresh_minutes": 30,
    "yahoo_cache_seconds": 60,
    "holidays": [],
    "early_closes": {},
}


def market_config_path() -> Path:
    """Return the configured schedule path, allowing an environment override."""
    override = os.getenv("MARKET_HOURS_CONFIG")
    return Path(override).expanduser() if override else DEFAULT_CONFIG_PATH


def load_market_config(path: Path | None = None) -> dict[str, Any]:
    """Load and lightly validate the market-hours configuration."""
    config = dict(DEFAULT_CONFIG)
    config_path = path or market_config_path()
    if config_path.exists():
        with config_path.open(encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, dict):
            raise ValueError(f"Market-hours config must be a JSON object: {config_path}")
        config.update(loaded)

    ZoneInfo(str(config["timezone"]))
    _parse_clock(str(config["open_time"]))
    _parse_clock(str(config["close_time"]))
    refresh_minutes = int(config["refresh_minutes"])
    cache_seconds = int(config["yahoo_cache_seconds"])
    if refresh_minutes <= 0:
        raise ValueError("refresh_minutes must be greater than zero")
    if cache_seconds < 0:
        raise ValueError("yahoo_cache_seconds cannot be negative")
    config["refresh_minutes"] = refresh_minutes
    config["yahoo_cache_seconds"] = cache_seconds
    config["weekdays"] = [int(day) for day in config["weekdays"]]
    return config


def _parse_clock(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid market time {value!r}; expected HH:MM") from exc


def _session_for(day: date, config: dict[str, Any], tz: ZoneInfo) -> tuple[datetime, datetime] | None:
    iso_day = day.isoformat()
    if day.weekday() not in config["weekdays"] or iso_day in set(config.get("holidays", [])):
        return None

    close_value = config.get("early_closes", {}).get(iso_day, config["close_time"])
    opens_at = datetime.combine(day, _parse_clock(str(config["open_time"])), tzinfo=tz)
    closes_at = datetime.combine(day, _parse_clock(str(close_value)), tzinfo=tz)
    if closes_at <= opens_at:
        raise ValueError(f"Market close must be after open for {iso_day}")
    return opens_at, closes_at


def _next_open(after: datetime, config: dict[str, Any], tz: ZoneInfo) -> datetime:
    for offset in range(15):
        day = after.date() + timedelta(days=offset)
        session = _session_for(day, config, tz)
        if session and session[0] > after:
            return session[0]
    raise ValueError("No market session found in the next 15 days; check the config")


def get_market_status(
    now: datetime | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return current session state and the next scheduled dashboard refresh."""
    cfg = config or load_market_config()
    tz = ZoneInfo(str(cfg["timezone"]))
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local_now = current.astimezone(tz)
    session = _session_for(local_now.date(), cfg, tz)
    is_open = bool(session and session[0] <= local_now < session[1])

    if is_open and session:
        interval = timedelta(minutes=int(cfg["refresh_minutes"]))
        elapsed = local_now - session[0]
        steps = int(elapsed.total_seconds() // interval.total_seconds()) + 1
        next_refresh = session[0] + (interval * steps)
        if next_refresh >= session[1]:
            next_refresh = _next_open(local_now, cfg, tz)
    else:
        next_refresh = _next_open(local_now, cfg, tz)

    opens_at = session[0] if session else None
    closes_at = session[1] if session else None
    return {
        "market": cfg["market"],
        "timezone": cfg["timezone"],
        "is_open": is_open,
        "current_time": local_now.isoformat(),
        "session_open": opens_at.isoformat() if opens_at else None,
        "session_close": closes_at.isoformat() if closes_at else None,
        "next_refresh_at": next_refresh.isoformat(),
        "refresh_minutes": cfg["refresh_minutes"],
        "yahoo_cache_seconds": cfg["yahoo_cache_seconds"],
    }

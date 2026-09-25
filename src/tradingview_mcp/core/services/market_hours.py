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
    "active_trading_window": "regular market",
    "trading_windows": {
        "regular market": {"start_time": "09:30", "end_time": "16:00"},
        "pre-market": {"start_time": "04:00", "end_time": "16:00"},
        "after hours": {"start_time": "09:30", "end_time": "20:00"},
        "extended hours": {"start_time": "04:00", "end_time": "20:00"},
        "overnight": {"start_time": "00:00", "end_time": "24:00"},
    },
    "refresh_minutes": 30,
    "yahoo_cache_seconds": 60,
    "holidays": [],
    "early_closes": {},
}

TRADING_WINDOW_ALIASES = {
    "regular": "regular market",
    "regular_market": "regular market",
    "regular market": "regular market",
    "premarket": "pre-market",
    "pre_market": "pre-market",
    "pre-market": "pre-market",
    "afterhours": "after hours",
    "after_hours": "after hours",
    "after hours": "after hours",
    "extended": "extended hours",
    "extended_hours": "extended hours",
    "extended hours": "extended hours",
    "overnight": "overnight",
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
    active_window = normalize_trading_window(str(config["active_trading_window"]), config)
    config["active_trading_window"] = active_window
    for name, window in config["trading_windows"].items():
        _parse_clock(str(window["start_time"]))
        if str(window["end_time"]) != "24:00":
            _parse_clock(str(window["end_time"]))
    return config


def _parse_clock(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid market time {value!r}; expected HH:MM") from exc


def normalize_trading_window(value: str | None, config: dict[str, Any] | None = None) -> str:
    """Normalize UI/config aliases and reject unsupported trading windows."""
    cfg = config or DEFAULT_CONFIG
    requested = value or str(cfg.get("active_trading_window", "regular market"))
    normalized = TRADING_WINDOW_ALIASES.get(requested.strip().lower(), requested.strip().lower())
    if normalized not in cfg["trading_windows"]:
        choices = ", ".join(cfg["trading_windows"])
        raise ValueError(f"Unsupported trading window {requested!r}; choose one of: {choices}")
    return normalized


def _window_datetimes(day: date, config: dict[str, Any], tz: ZoneInfo, trading_window: str) -> tuple[datetime, datetime]:
    window = config["trading_windows"][trading_window]
    opens_at = datetime.combine(day, _parse_clock(str(window["start_time"])), tzinfo=tz)
    end_value = str(window["end_time"])
    if end_value == "24:00":
        closes_at = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    else:
        closes_at = datetime.combine(day, _parse_clock(end_value), tzinfo=tz)
    return opens_at, closes_at


def _session_for(day: date, config: dict[str, Any], tz: ZoneInfo, trading_window: str) -> tuple[datetime, datetime] | None:
    iso_day = day.isoformat()
    if day.weekday() not in config["weekdays"] or iso_day in set(config.get("holidays", [])):
        return None

    opens_at, closes_at = _window_datetimes(day, config, tz, trading_window)
    close_value = config.get("early_closes", {}).get(iso_day)
    if close_value and trading_window != "overnight":
        early_close = datetime.combine(day, _parse_clock(str(close_value)), tzinfo=tz)
        closes_at = min(closes_at, early_close)
    if closes_at <= opens_at:
        raise ValueError(f"Market close must be after open for {iso_day}")
    return opens_at, closes_at


def _next_open(after: datetime, config: dict[str, Any], tz: ZoneInfo, trading_window: str) -> datetime:
    for offset in range(15):
        day = after.date() + timedelta(days=offset)
        session = _session_for(day, config, tz, trading_window)
        if session and session[0] > after:
            return session[0]
    raise ValueError("No market session found in the next 15 days; check the config")


def get_market_status(
    now: datetime | None = None,
    config: dict[str, Any] | None = None,
    trading_window: str | None = None,
) -> dict[str, Any]:
    """Return current session state and the next scheduled dashboard refresh."""
    cfg = config or load_market_config()
    selected_window = normalize_trading_window(trading_window, cfg)
    tz = ZoneInfo(str(cfg["timezone"]))
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local_now = current.astimezone(tz)
    session = _session_for(local_now.date(), cfg, tz, selected_window)
    is_open = bool(session and session[0] <= local_now < session[1])

    if is_open and session:
        interval = timedelta(minutes=int(cfg["refresh_minutes"]))
        elapsed = local_now - session[0]
        steps = int(elapsed.total_seconds() // interval.total_seconds()) + 1
        next_refresh = session[0] + (interval * steps)
        if next_refresh >= session[1]:
            next_refresh = _next_open(local_now, cfg, tz, selected_window)
    else:
        next_refresh = _next_open(local_now, cfg, tz, selected_window)

    opens_at = session[0] if session else None
    closes_at = session[1] if session else None
    return {
        "market": cfg["market"],
        "timezone": cfg["timezone"],
        "active_trading_window": selected_window,
        "configured_default_window": cfg["active_trading_window"],
        "available_trading_windows": list(cfg["trading_windows"]),
        "is_open": is_open,
        "current_time": local_now.isoformat(),
        "session_open": opens_at.isoformat() if opens_at else None,
        "session_close": closes_at.isoformat() if closes_at else None,
        "next_refresh_at": next_refresh.isoformat(),
        "refresh_minutes": cfg["refresh_minutes"],
        "yahoo_cache_seconds": cfg["yahoo_cache_seconds"],
    }


def timestamp_in_trading_window(
    value: datetime,
    trading_window: str,
    config: dict[str, Any] | None = None,
) -> bool:
    """Return whether an intraday candle timestamp belongs to the selected window."""
    cfg = config or load_market_config()
    selected_window = normalize_trading_window(trading_window, cfg)
    if selected_window == "overnight":
        return True
    tz = ZoneInfo(str(cfg["timezone"]))
    current = value
    if current.tzinfo is None:
        current = current.replace(tzinfo=tz)
    local = current.astimezone(tz)
    opens_at, closes_at = _window_datetimes(local.date(), cfg, tz, selected_window)
    return opens_at <= local < closes_at


def market_session_label(value: datetime, config: dict[str, Any] | None = None) -> str:
    """Classify a timestamp into the US equity session shown on the chart."""
    cfg = config or load_market_config()
    tz = ZoneInfo(str(cfg["timezone"]))
    current = value
    if current.tzinfo is None:
        current = current.replace(tzinfo=tz)
    clock = current.astimezone(tz).time().replace(tzinfo=None)
    if time(4, 0) <= clock < time(9, 30):
        return "pre-market"
    if time(9, 30) <= clock < time(16, 0):
        return "regular market"
    if time(16, 0) <= clock < time(20, 0):
        return "after hours"
    return "overnight"

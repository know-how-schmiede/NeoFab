from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


UTC_TIMEZONE = ZoneInfo("UTC")
DEFAULT_APP_TIMEZONE = "Europe/Berlin"
DEFAULT_DATETIME_FORMAT = "%Y-%m-%d %H:%M"


def get_app_timezone() -> ZoneInfo:
    timezone_name = os.environ.get("NEOFAB_TIMEZONE", DEFAULT_APP_TIMEZONE)
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return UTC_TIMEZONE


def get_app_timezone_name() -> str:
    return getattr(get_app_timezone(), "key", "UTC")


def _offset_hours(settings: Mapping[str, object] | None) -> int:
    if not settings:
        return 0
    try:
        return int(settings.get("time_display_offset_hours", 0) or 0)
    except Exception:
        return 0


def to_app_datetime(
    value: datetime | None,
    settings: Mapping[str, object] | None = None,
    *,
    apply_display_offset: bool = True,
) -> datetime | None:
    if value is None:
        return None

    try:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC_TIMEZONE)
        local_value = value.astimezone(get_app_timezone())
    except Exception:
        local_value = value

    if apply_display_offset:
        offset_hours = _offset_hours(settings)
        if offset_hours:
            local_value = local_value + timedelta(hours=offset_hours)

    return local_value


def format_app_datetime(
    value: datetime | None,
    settings: Mapping[str, object] | None = None,
    fmt: str = DEFAULT_DATETIME_FORMAT,
) -> str:
    local_value = to_app_datetime(value, settings)
    if local_value is None:
        return ""
    try:
        return local_value.strftime(fmt)
    except Exception:
        return ""


def parse_app_datetime_input(
    value: str | None,
    settings: Mapping[str, object] | None = None,
) -> datetime | None:
    raw_value = (value or "").strip()
    if not raw_value:
        return None

    parsed_value = datetime.fromisoformat(raw_value)
    if parsed_value.tzinfo is not None:
        return parsed_value.astimezone(UTC_TIMEZONE).replace(tzinfo=None)

    offset_hours = _offset_hours(settings)
    if offset_hours:
        parsed_value = parsed_value - timedelta(hours=offset_hours)

    local_value = parsed_value.replace(tzinfo=get_app_timezone())
    return local_value.astimezone(UTC_TIMEZONE).replace(tzinfo=None)

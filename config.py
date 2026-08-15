"""Configuration for the hackathon dashboard, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

DEFAULT_API_BASE = "https://aiau.devinenterprise.com/api"


def _parse_time(value: str) -> int:
    """Parse a unix timestamp or an ISO-8601 datetime (JST when no offset given)."""
    value = value.strip()
    if value.isdigit():
        return int(value)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JST)
    return int(parsed.timestamp())


@dataclass(frozen=True)
class Config:
    api_base: str
    api_key: str
    db_path: str
    port: int
    poll_interval: int
    org_refresh_interval: int
    hackathon_start: int | None
    hackathon_end: int | None
    max_hours: int

    @classmethod
    def from_env(cls) -> "Config":
        start = os.environ.get("HACKATHON_START", "").strip()
        end = os.environ.get("HACKATHON_END", "").strip()
        return cls(
            api_base=os.environ.get("DEVIN_API_BASE", DEFAULT_API_BASE).rstrip("/"),
            api_key=os.environ.get("DEVIN_ENTERPRISE_API_KEY", ""),
            db_path=os.environ.get("DASHBOARD_DB", "dashboard.db"),
            port=int(os.environ.get("PORT", "8787")),
            poll_interval=int(os.environ.get("POLL_INTERVAL", "60")),
            org_refresh_interval=int(os.environ.get("ORG_REFRESH_INTERVAL", "600")),
            hackathon_start=_parse_time(start) if start else None,
            hackathon_end=_parse_time(end) if end else None,
            max_hours=int(os.environ.get("MAX_HOURS", "72")),
        )

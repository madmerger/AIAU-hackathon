"""Offline checks for the collector and aggregation logic (no API access)."""

from __future__ import annotations

import time
from typing import Any

import store
from aggregate import build_payload
from collector import Collector, hour_of
from config import Config

NOW = int(time.time())
HOUR = 3600


class FakeClient:
    def __init__(self, sessions: list[dict[str, Any]]) -> None:
        self.sessions = sessions

    def list_organizations(self) -> list[dict[str, Any]]:
        return [
            {"org_id": "org-a", "name": "Team A", "created_at": NOW - 4 * HOUR},
            {"org_id": "org-b", "name": "Team B", "created_at": NOW - 4 * HOUR},
            {"org_id": "org-c", "name": "Team C", "created_at": NOW - 4 * HOUR},
        ]

    def list_org_users(self, org_id: str) -> list[dict[str, Any]]:
        users = {
            "org-a": ["shared-1", "org-a-user-1", "org-a-user-2"],
            "org-b": ["shared-1", "org-b-user-1"],
            "org-c": ["shared-1", "org-c-user-1", "org-c-user-2", "org-c-user-3"],
        }
        return [{"user_id": user_id} for user_id in users[org_id]]

    def list_sessions(self) -> list[dict[str, Any]]:
        return self.sessions


def session(
    session_id: str,
    org_id: str,
    created_at: int,
    acus: float,
    prs: list[tuple[str, str]],
    user_id: str | None = None,
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "org_id": org_id,
        "user_id": user_id or f"{org_id}-user-0",
        "title": f"session {session_id}",
        "url": f"https://example.com/{session_id}",
        "status": "running",
        "status_detail": "working",
        "devin_mode": "normal",
        "origin": "webapp",
        "created_at": created_at,
        "updated_at": created_at + 60,
        "acus_consumed": acus,
        "pull_requests": [{"pr_url": url, "pr_state": state} for url, state in prs],
    }


def main() -> None:
    config = Config(
        api_base="http://unused",
        api_key="unused",
        db_path=":memory:",
        port=0,
        poll_interval=60,
        org_refresh_interval=600,
        hackathon_start=NOW - 3 * HOUR,
        hackathon_end=NOW + 2 * HOUR,
        max_hours=72,
    )
    connection = store.connect(config.db_path)
    sessions = [
        session("s1", "org-a", NOW - 2 * HOUR, 10.0, [("pr1", "merged"), ("pr2", "open")], "shared-1"),
        session("s2", "org-b", NOW - 1 * HOUR, 4.0, [("pr3", "open")], "shared-1"),
    ]
    client = FakeClient(sessions)
    collector = Collector(client, connection)  # type: ignore[arg-type]

    collector.poll()
    payload = build_payload(connection, config, {"last_poll_at": NOW, "last_error": None, "poll_interval": 60})
    assert payload["totals"]["acus"] == 14.0, payload["totals"]
    assert payload["totals"]["prs_created"] == 3
    assert payload["totals"]["prs_merged"] == 1
    assert payload["totals"]["merge_rate"] == 33.3
    assert payload["totals"]["users"] == 7
    assert payload["totals"]["active_users"] == 1
    assert [entry["session_id"] for entry in payload["top_sessions"]] == ["s1", "s2"]
    assert [entry["acus"] for entry in payload["top_sessions"]] == [10.0, 4.0]
    assert payload["totals"]["active_orgs"] == 2
    assert [entry["name"] for entry in payload["orgs"][:2]] == ["Team A", "Team B"]
    assert payload["idle_orgs"][0]["name"] == "Team C"

    backfilled = {row["hour"]: row["acus"] for row in payload["hourly"]}
    assert backfilled[hour_of(NOW - 2 * HOUR)] == 10.0, backfilled
    assert backfilled[hour_of(NOW - HOUR)] == 4.0, backfilled

    sessions[0]["acus_consumed"] = 25.0
    sessions[0]["pull_requests"][1]["pr_state"] = "merged"
    sessions.append(session("s3", "org-c", NOW, 2.0, [], "shared-2"))
    collector.poll()
    payload = build_payload(connection, config, {"last_poll_at": NOW, "last_error": None, "poll_interval": 60})
    assert payload["totals"]["acus"] == 31.0, payload["totals"]
    assert payload["totals"]["prs_merged"] == 2
    assert payload["totals"]["active_orgs"] == 3
    assert payload["totals"]["users"] == 7
    assert payload["totals"]["active_users"] == 2
    assert [entry["session_id"] for entry in payload["top_sessions"]] == ["s1", "s2", "s3"]
    current = {row["hour"]: row["acus"] for row in payload["hourly"]}
    assert current[hour_of(NOW)] == 17.0, current  # 15 delta on s1 + 2 from the new session
    assert current[hour_of(NOW - 2 * HOUR)] == 10.0, current
    merged_now = {row["hour"]: row["prs_merged"] for row in payload["hourly"]}
    assert merged_now[hour_of(NOW)] == 1, merged_now

    assert sum(row["acus"] for row in payload["hourly"]) == payload["totals"]["acus"]
    assert payload["hourly"][-1]["acus_cum"] == payload["totals"]["acus"]
    print("selftest ok")


if __name__ == "__main__":
    main()

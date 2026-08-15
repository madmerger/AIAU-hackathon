"""Builds the JSON payload consumed by the dashboard front-end."""

from __future__ import annotations

import sqlite3
import time
from typing import Any

from collector import HOUR, hour_of
from config import Config

HEATMAP_ORGS = 12
RECENT_SESSIONS = 25
ERROR_STATUSES = ("error",)
ACTIVE_STATUSES = ("running", "resuming", "claimed", "new")


def _rate(numerator: float, denominator: float) -> float | None:
    return round(numerator / denominator * 100, 1) if denominator else None


def _hours_axis(connection: sqlite3.Connection, config: Config, now: int) -> list[int]:
    row = connection.execute(
        "SELECT MIN(hour_ts) AS first_hour FROM acu_hourly WHERE acus > 0"
    ).fetchone()
    earliest = row["first_hour"] if row and row["first_hour"] is not None else hour_of(now)
    start = hour_of(config.hackathon_start) if config.hackathon_start else int(earliest)
    start = min(start, int(earliest))
    end = hour_of(min(now, config.hackathon_end) if config.hackathon_end else now)
    hours = list(range(start, end + HOUR, HOUR))
    return hours[-config.max_hours :]


def build_payload(connection: sqlite3.Connection, config: Config, collector_state: dict[str, Any]) -> dict[str, Any]:
    now = int(time.time())
    hours = _hours_axis(connection, config, now)
    hour_index = {hour: position for position, hour in enumerate(hours)}
    bucket_count = len(hours)

    orgs = {
        row["org_id"]: {
            "org_id": row["org_id"],
            "name": row["name"],
            "user_count": int(row["user_count"]),
            "acus": 0.0,
            "sessions": 0,
            "active_users": 0,
            "prs_created": 0,
            "prs_merged": 0,
            "last_activity": None,
            "hourly_acus": [0.0] * bucket_count,
        }
        for row in connection.execute("SELECT org_id, name, user_count FROM orgs")
    }

    def org_entry(org_id: str) -> dict[str, Any]:
        if org_id not in orgs:
            orgs[org_id] = {
                "org_id": org_id,
                "name": org_id,
                "user_count": 0,
                "acus": 0.0,
                "sessions": 0,
                "active_users": 0,
                "prs_created": 0,
                "prs_merged": 0,
                "last_activity": None,
                "hourly_acus": [0.0] * bucket_count,
            }
        return orgs[org_id]

    hourly_acus = [0.0] * bucket_count
    for row in connection.execute("SELECT hour_ts, org_id, acus FROM acu_hourly"):
        position = hour_index.get(int(row["hour_ts"]))
        if position is None:
            continue
        hourly_acus[position] += float(row["acus"])
        org_entry(row["org_id"])["hourly_acus"][position] += float(row["acus"])

    hourly_prs_created = [0] * bucket_count
    hourly_prs_merged = [0] * bucket_count
    for row in connection.execute("SELECT org_id, state, created_hour, merged_hour FROM prs"):
        entry = org_entry(row["org_id"])
        entry["prs_created"] += 1
        created_position = hour_index.get(int(row["created_hour"] or 0))
        if created_position is not None:
            hourly_prs_created[created_position] += 1
        if row["merged_hour"] is not None:
            entry["prs_merged"] += 1
            merged_position = hour_index.get(int(row["merged_hour"]))
            if merged_position is not None:
                hourly_prs_merged[merged_position] += 1

    hourly_sessions = [0] * bucket_count
    statuses: dict[str, int] = {}
    modes: dict[str, int] = {}
    active_users_by_org: dict[str, set[str]] = {}
    active_user_ids: set[str] = set()
    total_acus = 0.0
    total_sessions = 0
    active_sessions = 0
    error_sessions = 0
    for row in connection.execute(
        "SELECT org_id, user_id, status, devin_mode, created_at, updated_at, acus FROM sessions"
    ):
        entry = org_entry(row["org_id"])
        entry["sessions"] += 1
        entry["acus"] += float(row["acus"])
        updated_at = int(row["updated_at"] or 0)
        if entry["last_activity"] is None or updated_at > entry["last_activity"]:
            entry["last_activity"] = updated_at
        if row["user_id"]:
            active_users_by_org.setdefault(row["org_id"], set()).add(row["user_id"])
            active_user_ids.add(row["user_id"])
        position = hour_index.get(hour_of(int(row["created_at"] or now)))
        if position is not None:
            hourly_sessions[position] += 1
        status = row["status"] or "unknown"
        statuses[status] = statuses.get(status, 0) + 1
        mode = row["devin_mode"] or "unknown"
        modes[mode] = modes.get(mode, 0) + 1
        total_acus += float(row["acus"])
        total_sessions += 1
        active_sessions += 1 if status in ACTIVE_STATUSES else 0
        error_sessions += 1 if status in ERROR_STATUSES else 0

    for org_id, users in active_users_by_org.items():
        org_entry(org_id)["active_users"] = len(users)

    hourly: list[dict[str, Any]] = []
    acus_cum = 0.0
    created_cum = 0
    merged_cum = 0
    for position, hour in enumerate(hours):
        acus_cum += hourly_acus[position]
        created_cum += hourly_prs_created[position]
        merged_cum += hourly_prs_merged[position]
        hourly.append(
            {
                "hour": hour,
                "acus": round(hourly_acus[position], 2),
                "acus_cum": round(acus_cum, 2),
                "prs_created": hourly_prs_created[position],
                "prs_merged": hourly_prs_merged[position],
                "prs_created_cum": created_cum,
                "prs_merged_cum": merged_cum,
                "merge_rate": _rate(hourly_prs_merged[position], hourly_prs_created[position]),
                "merge_rate_cum": _rate(merged_cum, created_cum),
                "sessions": hourly_sessions[position],
            }
        )

    org_rows = sorted(orgs.values(), key=lambda item: item["acus"], reverse=True)
    for rank, entry in enumerate(org_rows, start=1):
        entry["rank"] = rank
        entry["acus"] = round(entry["acus"], 2)
        entry["hourly_acus"] = [round(value, 2) for value in entry["hourly_acus"]]
        entry["merge_rate"] = _rate(entry["prs_merged"], entry["prs_created"])
        entry["acus_per_user"] = round(entry["acus"] / entry["user_count"], 2) if entry["user_count"] else None
        entry["prs_merged_per_user"] = (
            round(entry["prs_merged"] / entry["user_count"], 2) if entry["user_count"] else None
        )

    total_prs_created = sum(entry["prs_created"] for entry in org_rows)
    total_prs_merged = sum(entry["prs_merged"] for entry in org_rows)
    total_users = int(
        connection.execute("SELECT COUNT(DISTINCT user_id) AS count FROM org_users").fetchone()["count"]
    )
    total_active_users = len(active_user_ids)
    active_orgs = [entry for entry in org_rows if entry["sessions"] > 0]
    idle_orgs = [
        {"org_id": entry["org_id"], "name": entry["name"], "user_count": entry["user_count"]}
        for entry in org_rows
        if entry["sessions"] == 0
    ]

    previous_hour_acus = hourly[-2]["acus"] if len(hourly) >= 2 else 0.0
    current_hour_acus = hourly[-1]["acus"] if hourly else 0.0
    remaining_seconds = max(0, config.hackathon_end - now) if config.hackathon_end else None
    projected_total = None
    if remaining_seconds:
        projected_total = round(total_acus + previous_hour_acus * remaining_seconds / HOUR, 1)

    recent_sessions = [
        {
            "session_id": row["session_id"],
            "org_name": orgs.get(row["org_id"], {}).get("name", row["org_id"]),
            "title": row["title"],
            "url": row["url"],
            "status": row["status"],
            "status_detail": row["status_detail"],
            "devin_mode": row["devin_mode"],
            "acus": round(float(row["acus"]), 2),
            "updated_at": int(row["updated_at"] or 0),
            "prs_merged": int(row["prs_merged"] or 0),
        }
        for row in connection.execute(
            """
            SELECT s.session_id, s.org_id, s.title, s.url, s.status, s.status_detail,
                   s.devin_mode, s.acus, s.updated_at,
                   (SELECT COUNT(*) FROM prs WHERE prs.session_id = s.session_id
                     AND prs.merged_hour IS NOT NULL) AS prs_merged
            FROM sessions s ORDER BY s.updated_at DESC LIMIT ?
            """,
            (RECENT_SESSIONS,),
        )
    ]

    heatmap_orgs = [entry for entry in org_rows if entry["acus"] > 0][:HEATMAP_ORGS]
    return {
        "generated_at": now,
        "hours": hours,
        "hackathon": {
            "start": config.hackathon_start,
            "end": config.hackathon_end,
            "remaining_seconds": remaining_seconds,
        },
        "collector": collector_state,
        "totals": {
            "acus": round(total_acus, 2),
            "sessions": total_sessions,
            "active_sessions": active_sessions,
            "error_sessions": error_sessions,
            "prs_created": total_prs_created,
            "prs_merged": total_prs_merged,
            "prs_open": total_prs_created - total_prs_merged,
            "merge_rate": _rate(total_prs_merged, total_prs_created),
            "orgs": len(org_rows),
            "active_orgs": len(active_orgs),
            "users": total_users,
            "active_users": total_active_users,
            "activation_rate": _rate(total_active_users, total_users),
            "acus_per_session": round(total_acus / total_sessions, 2) if total_sessions else 0,
            "acus_per_merged_pr": round(total_acus / total_prs_merged, 2) if total_prs_merged else None,
        },
        "pace": {
            "acus_last_full_hour": previous_hour_acus,
            "acus_current_hour": current_hour_acus,
            "projected_total_acus": projected_total,
        },
        "hourly": hourly,
        "orgs": org_rows,
        "idle_orgs": idle_orgs,
        "statuses": statuses,
        "modes": modes,
        "heatmap": {
            "orgs": [{"name": entry["name"], "values": entry["hourly_acus"]} for entry in heatmap_orgs],
        },
        "recent_sessions": recent_sessions,
    }

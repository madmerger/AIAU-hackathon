"""Polls the Devin enterprise API and persists per-hour hackathon metrics.

ACU is reported per session as a cumulative value, and pull requests carry no
event timestamp, so hourly series are built from deltas between polls:

* a session seen for the first time contributes its ACU to the hour of its
  ``created_at`` (this backfills history on the very first poll),
* afterwards, every ACU increment is booked to the hour the poll observed it,
* a pull request is booked to the hour it was first observed, and its merge to
  the hour the ``merged`` state was first observed (both fall back to the
  session's creation hour when discovered on the first poll).
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from typing import Any

from devin_api import DevinApiError, DevinEnterpriseClient

HOUR = 3600
logger = logging.getLogger(__name__)


def hour_of(timestamp: int) -> int:
    return (int(timestamp) // HOUR) * HOUR


class Collector:
    def __init__(
        self,
        client: DevinEnterpriseClient,
        connection: sqlite3.Connection,
        org_refresh_interval: int = 600,
    ) -> None:
        self._client = client
        self._connection = connection
        self._org_refresh_interval = org_refresh_interval
        self._lock = threading.Lock()
        self._last_org_refresh = 0.0
        self.last_poll_at: int | None = None
        self.last_error: str | None = None

    def poll(self) -> None:
        with self._lock:
            now = int(time.time())
            try:
                if now - self._last_org_refresh >= self._org_refresh_interval:
                    self._refresh_orgs(now)
                    self._last_org_refresh = now
                sessions = self._client.list_sessions()
                first_poll = self._is_first_poll()
                for session in sessions:
                    self._apply_session(session, now=now, first_poll=first_poll)
                self._connection.execute(
                    "INSERT OR REPLACE INTO polls (ts, sessions_seen, error) VALUES (?, ?, NULL)",
                    (now, len(sessions)),
                )
                self._connection.commit()
                self.last_poll_at = now
                self.last_error = None
            except DevinApiError as error:
                self._connection.execute(
                    "INSERT OR REPLACE INTO polls (ts, sessions_seen, error) VALUES (?, 0, ?)",
                    (now, str(error)),
                )
                self._connection.commit()
                self.last_error = str(error)
                logger.warning("poll failed: %s", error)

    def run_forever(self, interval: int) -> None:
        while True:
            self.poll()
            time.sleep(interval)

    def _is_first_poll(self) -> bool:
        row = self._connection.execute("SELECT COUNT(*) AS n FROM polls WHERE error IS NULL").fetchone()
        return int(row["n"]) == 0

    def _refresh_orgs(self, now: int) -> None:
        for org in self._client.list_organizations():
            org_id = org["org_id"]
            try:
                users = self._client.list_org_users(org_id)
                self._connection.execute("DELETE FROM org_users WHERE org_id = ?", (org_id,))
                self._connection.executemany(
                    "INSERT OR IGNORE INTO org_users (org_id, user_id) VALUES (?, ?)",
                    [
                        (org_id, user["user_id"])
                        for user in users
                        if user.get("user_id")
                    ],
                )
                user_count = len(users)
            except DevinApiError as error:
                logger.warning("could not list users of %s: %s", org_id, error)
                row = self._connection.execute(
                    "SELECT user_count FROM orgs WHERE org_id = ?", (org_id,)
                ).fetchone()
                user_count = int(row["user_count"]) if row else 0
            self._connection.execute(
                """
                INSERT INTO orgs (org_id, name, user_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(org_id) DO UPDATE SET
                    name = excluded.name,
                    user_count = excluded.user_count,
                    updated_at = excluded.updated_at
                """,
                (org_id, org.get("name") or org_id, user_count, org.get("created_at"), now),
            )
        self._connection.commit()

    def _apply_session(self, session: dict[str, Any], now: int, first_poll: bool) -> None:
        session_id = session["session_id"]
        org_id = session.get("org_id") or "unknown"
        created_at = int(session.get("created_at") or now)
        acus = float(session.get("acus_consumed") or 0.0)
        previous = self._connection.execute(
            "SELECT acus FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()

        known_session = previous is not None
        if known_session:
            delta = acus - float(previous["acus"])
            bucket = hour_of(now)
        else:
            delta = acus
            bucket = hour_of(created_at)
        if delta > 0:
            self._add_acus(bucket, org_id, delta)

        self._connection.execute(
            """
            INSERT INTO sessions (
                session_id, org_id, user_id, title, url, status, status_detail,
                devin_mode, origin, created_at, updated_at, acus, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                org_id = excluded.org_id,
                title = excluded.title,
                status = excluded.status,
                status_detail = excluded.status_detail,
                devin_mode = excluded.devin_mode,
                updated_at = excluded.updated_at,
                acus = excluded.acus,
                last_seen = excluded.last_seen
            """,
            (
                session_id,
                org_id,
                session.get("user_id"),
                session.get("title"),
                session.get("url"),
                session.get("status"),
                session.get("status_detail"),
                session.get("devin_mode"),
                session.get("origin"),
                created_at,
                int(session.get("updated_at") or created_at),
                acus,
                now,
            ),
        )

        event_hour = hour_of(now) if known_session and not first_poll else hour_of(created_at)
        for pull_request in session.get("pull_requests") or []:
            self._apply_pull_request(pull_request, session_id, org_id, event_hour, now)

    def _apply_pull_request(
        self,
        pull_request: dict[str, Any],
        session_id: str,
        org_id: str,
        event_hour: int,
        now: int,
    ) -> None:
        url = pull_request.get("pr_url") or pull_request.get("url")
        if not url:
            return
        state = (pull_request.get("pr_state") or pull_request.get("state") or "").lower()
        existing = self._connection.execute(
            "SELECT created_hour, merged_hour FROM prs WHERE pr_url = ?", (url,)
        ).fetchone()
        if existing is None:
            merged_hour = event_hour if state == "merged" else None
            self._connection.execute(
                """
                INSERT INTO prs (pr_url, session_id, org_id, state, created_hour, merged_hour, first_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (url, session_id, org_id, state, event_hour, merged_hour, now),
            )
            return
        merged_hour = existing["merged_hour"]
        if state == "merged" and merged_hour is None:
            merged_hour = event_hour
        self._connection.execute(
            "UPDATE prs SET state = ?, merged_hour = ?, org_id = ?, session_id = ? WHERE pr_url = ?",
            (state, merged_hour, org_id, session_id, url),
        )

    def _add_acus(self, hour_ts: int, org_id: str, acus: float) -> None:
        self._connection.execute(
            """
            INSERT INTO acu_hourly (hour_ts, org_id, acus) VALUES (?, ?, ?)
            ON CONFLICT(hour_ts, org_id) DO UPDATE SET acus = acus + excluded.acus
            """,
            (hour_ts, org_id, acus),
        )

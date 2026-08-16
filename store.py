"""SQLite persistence for collected hackathon metrics."""

from __future__ import annotations

import sqlite3
from contextlib import closing

SCHEMA = """
CREATE TABLE IF NOT EXISTS orgs (
    org_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    user_count INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER,
    updated_at INTEGER
);
CREATE TABLE IF NOT EXISTS org_users (
    org_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    PRIMARY KEY (org_id, user_id)
);
CREATE TABLE IF NOT EXISTS org_summaries (
    org_id TEXT PRIMARY KEY,
    summary TEXT NOT NULL DEFAULT '',
    titles_hash TEXT NOT NULL DEFAULT '',
    updated_at INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    org_id TEXT,
    user_id TEXT,
    title TEXT,
    url TEXT,
    status TEXT,
    status_detail TEXT,
    devin_mode TEXT,
    origin TEXT,
    created_at INTEGER,
    updated_at INTEGER,
    acus REAL NOT NULL DEFAULT 0,
    last_seen INTEGER
);
CREATE TABLE IF NOT EXISTS prs (
    pr_url TEXT PRIMARY KEY,
    session_id TEXT,
    org_id TEXT,
    state TEXT,
    created_hour INTEGER,
    merged_hour INTEGER,
    first_seen INTEGER
);
CREATE TABLE IF NOT EXISTS acu_hourly (
    hour_ts INTEGER NOT NULL,
    org_id TEXT NOT NULL,
    acus REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (hour_ts, org_id)
);
CREATE TABLE IF NOT EXISTS polls (
    ts INTEGER PRIMARY KEY,
    sessions_seen INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_org ON sessions(org_id);
CREATE INDEX IF NOT EXISTS idx_prs_org ON prs(org_id);
CREATE INDEX IF NOT EXISTS idx_org_users_user ON org_users(user_id);
"""


def connect(db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    with closing(connection.cursor()) as cursor:
        cursor.executescript(SCHEMA)
    connection.commit()
    return connection

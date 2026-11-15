"""Database helpers and schema (built-in sqlite3, no ORM)."""
import os
import sqlite3

from flask import g

DB_PATH = os.environ.get(
    "TRACKER_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "tracker.db"),
)

SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    title TEXT NOT NULL,
    grp TEXT NOT NULL,              -- owner | pmo | finance | leadership
    approver_stage INTEGER          -- 1..5 when this person is the named approver
);

CREATE TABLE investments (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    owner_id INTEGER NOT NULL REFERENCES users(id),
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Draft',
    current_stage INTEGER,
    stage_entered TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    strategic_statement TEXT NOT NULL DEFAULT '',
    strategic_tags TEXT NOT NULL DEFAULT '',   -- '|' separated
    approach TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL DEFAULT '',
    deliverables TEXT NOT NULL DEFAULT '',
    assumptions TEXT NOT NULL DEFAULT '',
    dependencies TEXT NOT NULL DEFAULT '',
    risks TEXT NOT NULL DEFAULT ''
);

CREATE TABLE approvals (
    id INTEGER PRIMARY KEY,
    investment_id INTEGER NOT NULL REFERENCES investments(id),
    stage INTEGER NOT NULL,
    stage_name TEXT NOT NULL,
    approver_id INTEGER REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'Not yet reached',
    decision_date TEXT,
    comments TEXT NOT NULL DEFAULT '',
    conditions TEXT NOT NULL DEFAULT '',
    UNIQUE (investment_id, stage)
);

CREATE TABLE approval_history (
    id INTEGER PRIMARY KEY,
    investment_id INTEGER NOT NULL REFERENCES investments(id),
    stage INTEGER NOT NULL,
    stage_name TEXT NOT NULL,
    approver_id INTEGER,
    approver_name TEXT,
    decision TEXT NOT NULL,
    decision_date TEXT NOT NULL,
    comments TEXT NOT NULL DEFAULT '',
    conditions TEXT NOT NULL DEFAULT ''
);

CREATE TABLE costs (
    id INTEGER PRIMARY KEY,
    investment_id INTEGER NOT NULL REFERENCES investments(id),
    fy INTEGER NOT NULL,
    budget REAL NOT NULL DEFAULT 0,
    actual REAL NOT NULL DEFAULT 0,
    forecast REAL NOT NULL DEFAULT 0,
    UNIQUE (investment_id, fy)
);

CREATE TABLE fin_benefits (
    id INTEGER PRIMARY KEY,
    investment_id INTEGER NOT NULL REFERENCES investments(id),
    type TEXT NOT NULL,
    description TEXT NOT NULL,
    amount REAL NOT NULL,
    realised_amount REAL NOT NULL DEFAULT 0
);

CREATE TABLE nonfin_benefits (
    id INTEGER PRIMARY KEY,
    investment_id INTEGER NOT NULL REFERENCES investments(id),
    category TEXT NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE metrics (
    id INTEGER PRIMARY KEY,
    investment_id INTEGER NOT NULL REFERENCES investments(id),
    name TEXT NOT NULL,
    unit TEXT NOT NULL,
    direction TEXT NOT NULL,        -- higher | lower
    baseline REAL NOT NULL,
    target REAL NOT NULL,
    target_date TEXT NOT NULL,
    owner_id INTEGER REFERENCES users(id)
);

CREATE TABLE measurements (
    id INTEGER PRIMARY KEY,
    metric_id INTEGER NOT NULL REFERENCES metrics(id),
    date TEXT NOT NULL,
    value REAL NOT NULL
);

CREATE TABLE phases (
    id INTEGER PRIMARY KEY,
    investment_id INTEGER NOT NULL REFERENCES investments(id),
    position INTEGER NOT NULL,
    name TEXT NOT NULL,
    planned_start TEXT NOT NULL,
    planned_end TEXT NOT NULL,
    forecast_start TEXT,
    forecast_end TEXT,
    actual_start TEXT,
    actual_end TEXT,
    status TEXT NOT NULL DEFAULT 'Not started'
);

CREATE TABLE resources (
    id INTEGER PRIMARY KEY,
    investment_id INTEGER NOT NULL REFERENCES investments(id),
    phase_id INTEGER NOT NULL REFERENCES phases(id),
    role TEXT NOT NULL,
    ftes REAL NOT NULL
);

CREATE TABLE capacity_pool (
    role TEXT PRIMARY KEY,
    ftes REAL NOT NULL
);

CREATE TABLE reviews (
    id INTEGER PRIMARY KEY,
    investment_id INTEGER NOT NULL REFERENCES investments(id),
    months_after INTEGER NOT NULL,
    review_date TEXT,
    reviewer_id INTEGER REFERENCES users(id),
    findings TEXT NOT NULL DEFAULT '',
    lessons TEXT NOT NULL DEFAULT ''
);

CREATE TABLE audit (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    user_id INTEGER,
    user_name TEXT NOT NULL,
    investment_id INTEGER,
    area TEXT NOT NULL,
    field TEXT NOT NULL,
    old_value TEXT NOT NULL DEFAULT '',
    new_value TEXT NOT NULL DEFAULT ''
);
"""

STAGES = [
    (1, "Business Case"),
    (2, "Portfolio Manager review"),
    (3, "Finance Sign-off"),
    (4, "Technical / Architecture Review"),
    (5, "Investment Board"),
]


def connect(path=None):
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn):
    conn.executescript(SCHEMA)


def create_approval_rows(conn, investment_id):
    """Create the five fixed approval stage records for a new investment."""
    for stage, name in STAGES:
        approver = conn.execute(
            "SELECT id FROM users WHERE approver_stage = ?", (stage,)
        ).fetchone()
        conn.execute(
            "INSERT INTO approvals (investment_id, stage, stage_name, approver_id, status) "
            "VALUES (?, ?, ?, ?, 'Not yet reached')",
            (investment_id, stage, name, approver["id"] if approver else None),
        )


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()

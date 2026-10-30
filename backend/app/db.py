import sqlite3

from .config import settings

SCHEMA = """
DROP TABLE IF EXISTS findings;
DROP TABLE IF EXISTS turns;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS daily_counter;
CREATE TABLE sessions (
  id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, mode TEXT NOT NULL,
  started_at TEXT NOT NULL, ended_at TEXT, risk INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE turns (
  session_id TEXT NOT NULL, idx INTEGER NOT NULL, speaker TEXT NOT NULL, text TEXT NOT NULL,
  PRIMARY KEY (session_id, idx)
);
CREATE TABLE findings (
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, turn_idx INTEGER NOT NULL,
  rule_id TEXT NOT NULL, kind TEXT NOT NULL, confidence REAL NOT NULL, quote TEXT NOT NULL
);
CREATE TABLE daily_counter (day TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Data resets on every start (docs/01 §6)."""
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect()
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()

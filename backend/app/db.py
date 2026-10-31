import sqlite3

from .config import settings

SCHEMA = """
DROP TABLE IF EXISTS findings;
DROP TABLE IF EXISTS turns;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS daily_counter;
CREATE TABLE sessions (
  id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, mode TEXT NOT NULL,
  started_at TEXT NOT NULL, ended_at TEXT, risk_peak INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE turns (
  session_id TEXT NOT NULL, idx INTEGER NOT NULL, speaker TEXT NOT NULL, text TEXT NOT NULL,
  lang TEXT, stt_latency_ms INTEGER, PRIMARY KEY (session_id, idx)
);
CREATE TABLE findings (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL, turn_idx INTEGER NOT NULL, rule_id TEXT NOT NULL,
  kind TEXT NOT NULL, confidence REAL NOT NULL, quote TEXT NOT NULL, tok_start INTEGER, tok_end INTEGER,
  reason TEXT, rbi_ref TEXT, rewrite TEXT, source TEXT
);
CREATE INDEX findings_session ON findings(session_id);
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


# ---- session log and global daily cap (docs/02 §5; IST date) ----
def ist_day() -> str:
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d")


def try_take_slot(cap: int) -> bool:
    """Count one live session for today. False when the cap is reached (caller falls back to replay)."""
    conn = connect()
    try:
        with conn:
            conn.execute("INSERT OR IGNORE INTO daily_counter(day, count) VALUES (?, 0)", (ist_day(),))
            cur = conn.execute("UPDATE daily_counter SET count = count + 1 WHERE day = ? AND count < ?", (ist_day(), cap))
            return cur.rowcount == 1
    finally:
        conn.close()


def log_session_start(sid: str, scenario_id: str, mode: str, started_at: str) -> None:
    conn = connect()
    try:
        with conn:
            conn.execute("INSERT INTO sessions(id, scenario_id, mode, started_at) VALUES (?,?,?,?)",
                         (sid, scenario_id, mode, started_at))
    finally:
        conn.close()


def log_turn(sid: str, idx: int, speaker: str, text: str, lang: str, stt_ms: int) -> None:
    conn = connect()
    try:
        with conn:
            conn.execute("INSERT OR REPLACE INTO turns VALUES (?,?,?,?,?,?)", (sid, idx, speaker, text, lang, stt_ms))
    finally:
        conn.close()


def log_finding(sid: str, f: dict) -> None:
    conn = connect()
    try:
        with conn:
            conn.execute("INSERT OR REPLACE INTO findings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (f["id"], sid, f["turn_idx"], f["rule_id"], f["kind"], f["confidence"], f["quote"],
                          f["token_range"][0], f["token_range"][1], f.get("reason"), f.get("rbi_ref"),
                          f.get("rewrite"), f.get("source")))
    finally:
        conn.close()


def log_session_end(sid: str, ended_at: str, risk_peak: int) -> None:
    conn = connect()
    try:
        with conn:
            conn.execute("UPDATE sessions SET ended_at=?, risk_peak=? WHERE id=?", (ended_at, risk_peak, sid))
    finally:
        conn.close()


def session_summary(sid: str) -> dict | None:
    conn = connect()
    try:
        s = conn.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        if s is None:
            return None
        fs = [dict(r) for r in conn.execute("SELECT * FROM findings WHERE session_id=? ORDER BY turn_idx", (sid,))]
        return {"id": s["id"], "scenario_id": s["scenario_id"], "mode": s["mode"], "risk_peak": s["risk_peak"],
                "findings": fs, "ended_at": s["ended_at"]}
    finally:
        conn.close()

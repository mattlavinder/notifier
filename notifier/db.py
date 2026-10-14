import sqlite3
from pathlib import Path

from . import config

NOW = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS notifications (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at  TEXT NOT NULL DEFAULT ({NOW}),
  subject     TEXT NOT NULL,
  body_html   TEXT NOT NULL,
  source      TEXT,
  notified_at TEXT,
  read_at     TEXT
);
CREATE INDEX IF NOT EXISTS ix_pending ON notifications(notified_at) WHERE notified_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_unread ON notifications(read_at) WHERE read_at IS NULL;
"""

# Columns needed for list views; skips the (potentially large) HTML body.
SUMMARY_COLS = "id, created_at, subject, source, notified_at, read_at"


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(SCHEMA)
    return conn


def insert(conn, subject: str, body_html: str, source: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO notifications (subject, body_html, source) VALUES (?, ?, ?)",
        (subject, body_html, source),
    )
    return cur.lastrowid


def get(conn, notification_id: int):
    return conn.execute("SELECT * FROM notifications WHERE id = ?", (notification_id,)).fetchone()


def pending(conn):
    return conn.execute(
        f"SELECT {SUMMARY_COLS} FROM notifications WHERE notified_at IS NULL ORDER BY id"
    ).fetchall()


def mark_notified(conn, ids):
    conn.executemany(
        f"UPDATE notifications SET notified_at = {NOW} WHERE id = ? AND notified_at IS NULL",
        [(i,) for i in ids],
    )


def recent(conn, limit: int, offset: int = 0, unread_only: bool = False):
    where = "WHERE read_at IS NULL" if unread_only else ""
    return conn.execute(
        f"SELECT {SUMMARY_COLS} FROM notifications {where} ORDER BY id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()


def count(conn, unread_only: bool = False) -> int:
    where = "WHERE read_at IS NULL" if unread_only else ""
    return conn.execute(f"SELECT COUNT(*) FROM notifications {where}").fetchone()[0]


def set_read(conn, notification_id: int, read: bool):
    if read:
        conn.execute(
            f"UPDATE notifications SET read_at = {NOW} WHERE id = ? AND read_at IS NULL",
            (notification_id,),
        )
    else:
        conn.execute("UPDATE notifications SET read_at = NULL WHERE id = ?", (notification_id,))


def mark_all_read(conn):
    conn.execute(f"UPDATE notifications SET read_at = {NOW} WHERE read_at IS NULL")


def neighbors(conn, notification_id: int) -> tuple[int | None, int | None]:
    """Return (older_id, newer_id) around the given notification."""
    older = conn.execute(
        "SELECT MAX(id) FROM notifications WHERE id < ?", (notification_id,)
    ).fetchone()[0]
    newer = conn.execute(
        "SELECT MIN(id) FROM notifications WHERE id > ?", (notification_id,)
    ).fetchone()[0]
    return older, newer

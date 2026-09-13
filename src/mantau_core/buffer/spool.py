"""A durable, TTL-evicting queue backed by SQLite.

SQLite (not an in-memory list) is the point: the agent's uplink can die and
restart mid-outage — a fall detected right before a tunnel drop must still be
there when the agent comes back up. WAL mode keeps a concurrent reader (a
health-check route) from blocking the writer.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SpoolItem:
    item_id: str
    payload: str
    enqueued_at: float
    attempts: int


class DurableSpool:
    def __init__(self, path: str | Path, *, ttl_s: float = 300.0) -> None:
        """`ttl_s` is how long an unacked item is kept — the brief's "buffer
        recent frame/event data locally for a few minutes" (default 5 min)."""
        self.ttl_s = ttl_s
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS spool_items ("
            "  id TEXT PRIMARY KEY,"
            "  payload TEXT NOT NULL,"
            "  enqueued_at REAL NOT NULL,"
            "  attempts INTEGER NOT NULL DEFAULT 0"
            ")"
        )
        self._conn.commit()

    def put(self, item_id: str, payload: str, *, at: float | None = None) -> None:
        ts = at if at is not None else time.time()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO spool_items (id, payload, enqueued_at, attempts) "
                "VALUES (?, ?, ?, COALESCE((SELECT attempts FROM spool_items WHERE id = ?), 0))",
                (item_id, payload, ts, item_id),
            )
            self._conn.commit()

    def pending(self, limit: int = 100) -> list[SpoolItem]:
        """Oldest first — a retry loop should drain in enqueue order."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, payload, enqueued_at, attempts FROM spool_items "
                "ORDER BY enqueued_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [SpoolItem(item_id=r[0], payload=r[1], enqueued_at=r[2], attempts=r[3]) for r in rows]

    def mark_attempted(self, item_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE spool_items SET attempts = attempts + 1 WHERE id = ?", (item_id,)
            )
            self._conn.commit()

    def ack(self, item_id: str) -> None:
        """Remove an item once it has been successfully delivered onward."""
        with self._lock:
            self._conn.execute("DELETE FROM spool_items WHERE id = ?", (item_id,))
            self._conn.commit()

    def evict_expired(self, *, now: float | None = None) -> int:
        """Drop anything older than `ttl_s`. Returns how many were dropped."""
        cutoff = (now if now is not None else time.time()) - self.ttl_s
        with self._lock:
            cur = self._conn.execute("DELETE FROM spool_items WHERE enqueued_at < ?", (cutoff,))
            self._conn.commit()
            return cur.rowcount

    def depth(self) -> int:
        with self._lock:
            (count,) = self._conn.execute("SELECT COUNT(*) FROM spool_items").fetchone()
        return count

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "DurableSpool":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

"""A durable, capacity-bounded, TTL-evicting queue backed by SQLite.

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


class SpoolCapacityError(RuntimeError):
    """A write was rejected; all previously queued items remain unchanged."""

    def __init__(
        self, item_id: str, *, rows: int, size_bytes: int,
        projected_rows: int, projected_bytes: int, max_rows: int, max_bytes: int,
    ) -> None:
        self.item_id = item_id
        self.rows = rows
        self.size_bytes = size_bytes
        self.projected_rows = projected_rows
        self.projected_bytes = projected_bytes
        self.max_rows = max_rows
        self.max_bytes = max_bytes
        super().__init__(
            f"Spool capacity exceeded: {projected_rows}/{max_rows} rows, "
            f"{projected_bytes}/{max_bytes} bytes; write rejected"
        )


class DurableSpool:
    DEFAULT_MAX_ROWS = 10_000
    DEFAULT_MAX_BYTES = 16 * 1024 * 1024

    def __init__(
        self, path: str | Path, *, ttl_s: float = 300.0,
        max_rows: int = DEFAULT_MAX_ROWS, max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        """Keep unacked items for `ttl_s` (default 5 minutes).

        Capacity counts UTF-8 IDs and payloads, excluding SQLite/WAL overhead.
        Overflow rejects the incoming write instead of dropping pending items.
        Reopening an existing database with tighter limits preserves its rows;
        ack or explicit TTL eviction must free space before further writes.
        """
        for name, value in (("max_rows", max_rows), ("max_bytes", max_bytes)):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        self.ttl_s = ttl_s
        self.max_rows = max_rows
        self.max_bytes = max_bytes
        self._lock = threading.Lock()
        path = Path(path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
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
        """Persist a write, or raise SpoolCapacityError without changing rows.

        No implicit TTL eviction happens here: callers can account for expired
        items using the existing `evict_expired` result before retrying a write.
        """
        ts = at if at is not None else time.time()
        item_bytes = len(item_id.encode("utf-8")) + len(payload.encode("utf-8"))
        with self._lock, self._conn:
            # Serialize capacity checks across processes/connections as well as
            # threads, so two simultaneous producers cannot exceed a limit.
            self._conn.execute("BEGIN IMMEDIATE")
            rows, size_bytes = self._conn.execute(
                "SELECT COUNT(*), COALESCE(SUM("
                "length(CAST(id AS BLOB)) + length(CAST(payload AS BLOB))), 0) "
                "FROM spool_items"
            ).fetchone()
            previous = self._conn.execute(
                "SELECT length(CAST(id AS BLOB)) + length(CAST(payload AS BLOB)) "
                "FROM spool_items WHERE id = ?", (item_id,),
            ).fetchone()
            projected_rows = rows + (previous is None)
            projected_bytes = size_bytes - (previous[0] if previous else 0) + item_bytes
            if projected_rows > self.max_rows or projected_bytes > self.max_bytes:
                raise SpoolCapacityError(
                    item_id, rows=rows, size_bytes=size_bytes,
                    projected_rows=projected_rows, projected_bytes=projected_bytes,
                    max_rows=self.max_rows, max_bytes=self.max_bytes,
                )
            self._conn.execute(
                "INSERT OR REPLACE INTO spool_items (id, payload, enqueued_at, attempts) "
                "VALUES (?, ?, ?, COALESCE((SELECT attempts FROM spool_items WHERE id = ?), 0))",
                (item_id, payload, ts, item_id),
            )

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

    def size_bytes(self) -> int:
        """UTF-8 ID/payload bytes currently persisted, including expired rows."""
        with self._lock:
            (size,) = self._conn.execute(
                "SELECT COALESCE(SUM(length(CAST(id AS BLOB)) + "
                "length(CAST(payload AS BLOB))), 0) FROM spool_items"
            ).fetchone()
        return size

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "DurableSpool":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

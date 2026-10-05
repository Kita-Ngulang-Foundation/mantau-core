"""The one property that matters: an item survives a restart until acked or expired."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from mantau_core.buffer import DurableSpool
from mantau_core.buffer.spool import SpoolCapacityError


def test_put_then_pending_returns_oldest_first(tmp_path):
    with DurableSpool(tmp_path / "spool.db") as spool:
        spool.put("ev-1", '{"n": 1}', at=100.0)
        spool.put("ev-2", '{"n": 2}', at=101.0)
        items = spool.pending()
        assert [i.item_id for i in items] == ["ev-1", "ev-2"]


def test_ack_removes_the_item(tmp_path):
    with DurableSpool(tmp_path / "spool.db") as spool:
        spool.put("ev-1", "{}")
        spool.ack("ev-1")
        assert spool.pending() == []
        assert spool.depth() == 0


def test_survives_close_and_reopen_at_the_same_path(tmp_path):
    db_path = tmp_path / "spool.db"
    spool = DurableSpool(db_path)
    spool.put("ev-1", '{"fall": true}')
    spool.close()  # simulate the agent process restarting mid-outage

    reopened = DurableSpool(db_path)
    try:
        items = reopened.pending()
        assert len(items) == 1
        assert items[0].item_id == "ev-1"
        assert items[0].payload == '{"fall": true}'
    finally:
        reopened.close()


def test_evict_expired_drops_only_stale_items(tmp_path):
    with DurableSpool(tmp_path / "spool.db", ttl_s=60.0) as spool:
        spool.put("old", "{}", at=1000.0)
        spool.put("fresh", "{}", at=1990.0)
        dropped = spool.evict_expired(now=2000.0)  # old is 1000s stale, well past ttl
        assert dropped == 1
        assert [i.item_id for i in spool.pending()] == ["fresh"]


def test_mark_attempted_increments_the_retry_count(tmp_path):
    with DurableSpool(tmp_path / "spool.db") as spool:
        spool.put("ev-1", "{}")
        spool.mark_attempted("ev-1")
        spool.mark_attempted("ev-1")
        assert spool.pending()[0].attempts == 2


def test_reputting_the_same_id_preserves_attempts(tmp_path):
    with DurableSpool(tmp_path / "spool.db") as spool:
        spool.put("ev-1", "{}")
        spool.mark_attempted("ev-1")
        spool.put("ev-1", '{"updated": true}')  # e.g. clip finally attached
        item = spool.pending()[0]
        assert item.attempts == 1
        assert item.payload == '{"updated": true}'


def test_row_pressure_rejects_new_items_and_retains_pending_delivery(tmp_path):
    db_path = tmp_path / "spool.db"
    with DurableSpool(db_path, max_rows=3) as spool:
        for index in range(3):
            spool.put(f"fall-{index}", '{"fall": true}', at=float(index))
        spool.mark_attempted("fall-0")
        before = spool.pending()
        for index in range(3, 30):
            with pytest.raises(SpoolCapacityError) as rejected:
                spool.put(f"fall-{index}", '{"fall": true}')
            assert rejected.value.rows == 3
            assert rejected.value.projected_rows == 4
            assert rejected.value.max_rows == 3
        assert spool.pending() == before

    with DurableSpool(db_path, max_rows=3) as reopened:
        assert reopened.pending() == before
        for item in reopened.pending():
            reopened.ack(item.item_id)
        reopened.put("recovered", "{}")
        assert [item.item_id for item in reopened.pending()] == ["recovered"]


def test_byte_limit_counts_utf8_ids_and_payload_at_exact_boundary(tmp_path):
    # Unicode byte sizes and embedded NULs must not use SQLite TEXT length.
    item_id, payload = "警", "é\x00"
    expected_bytes = len((item_id + payload).encode("utf-8"))
    with DurableSpool(tmp_path / "spool.db", max_bytes=expected_bytes) as spool:
        spool.put(item_id, payload)
        assert spool.size_bytes() == expected_bytes
        with pytest.raises(SpoolCapacityError) as rejected:
            spool.put("x", "")
        assert rejected.value.size_bytes == expected_bytes
        assert rejected.value.projected_bytes == expected_bytes + 1
        assert rejected.value.max_bytes == expected_bytes
        assert spool.pending()[0].payload == payload


def test_oversized_item_is_not_stored_and_queue_can_still_accept_a_write(tmp_path):
    with DurableSpool(tmp_path / "spool.db", max_bytes=5) as spool:
        with pytest.raises(SpoolCapacityError):
            spool.put("id", "1234")
        assert spool.depth() == spool.size_bytes() == 0
        spool.put("id", "123")
        assert spool.size_bytes() == 5


def test_replacement_accounts_only_new_bytes_and_rejection_preserves_original(tmp_path):
    with DurableSpool(tmp_path / "spool.db", max_rows=1, max_bytes=8) as spool:
        spool.put("id", "123", at=10)
        spool.mark_attempted("id")
        spool.put("id", "123456", at=20)
        assert spool.depth() == 1
        assert spool.size_bytes() == 8
        previous = spool.pending()
        with pytest.raises(SpoolCapacityError):
            spool.put("id", "1234567", at=30)
        assert spool.pending() == previous
        spool.put("id", "x", at=40)
        assert spool.size_bytes() == 3
        assert spool.pending()[0].attempts == 1


def test_ttl_and_ack_release_capacity_without_implicit_expiration(tmp_path):
    with DurableSpool(tmp_path / "spool.db", ttl_s=60, max_rows=2, max_bytes=8) as spool:
        spool.put("a", "123", at=100)
        spool.put("b", "123", at=140)
        with pytest.raises(SpoolCapacityError):
            spool.put("c", "123", at=200)
        # The TTL boundary itself is retained; only strictly older rows expire.
        assert spool.evict_expired(now=160) == 0
        assert spool.size_bytes() == 8
        assert spool.evict_expired(now=161) == 1
        assert spool.size_bytes() == 4
        spool.put("c", "123", at=200)
        spool.ack("b")
        spool.ack("missing")
        assert spool.size_bytes() == 4
        spool.ack("c")
        assert spool.depth() == spool.size_bytes() == 0


def test_reopening_with_tighter_capacity_does_not_discard_pending_items(tmp_path):
    db_path = tmp_path / "spool.db"
    with DurableSpool(db_path) as spool:
        spool.put("a", "123")
        spool.put("b", "123")
    with DurableSpool(db_path, max_rows=1, max_bytes=4) as spool:
        assert spool.depth() == 2
        assert spool.size_bytes() == 8
        with pytest.raises(SpoolCapacityError):
            spool.put("c", "123")
        assert [item.item_id for item in spool.pending()] == ["a", "b"]
        spool.ack("a")
        spool.put("b", "x")
        assert spool.size_bytes() == 2


def test_independent_connections_cannot_overfill_the_same_queue(tmp_path):
    db_path = tmp_path / "spool.db"
    with DurableSpool(db_path, max_rows=1) as first, DurableSpool(
        db_path, max_rows=1,
    ) as second:
        start = Barrier(2)

        def write(spool, item_id):
            start.wait(timeout=5)
            try:
                spool.put(item_id, "{}")
            except SpoolCapacityError:
                return False
            return True

        with ThreadPoolExecutor(max_workers=2) as pool:
            attempts = [pool.submit(write, first, "a"), pool.submit(write, second, "b")]
            assert sorted(attempt.result(timeout=10) for attempt in attempts) == [False, True]
        assert first.depth() == second.depth() == 1
        assert first.pending() == second.pending()


@pytest.mark.parametrize("setting", ["max_rows", "max_bytes"])
@pytest.mark.parametrize("invalid", [0, -1, 1.5, True, None])
def test_capacity_limits_must_be_positive_integers(tmp_path, setting, invalid):
    with pytest.raises(ValueError, match=setting):
        DurableSpool(tmp_path / "spool.db", **{setting: invalid})
    assert not (tmp_path / "spool.db").exists()


def test_default_capacity_is_bounded(tmp_path):
    with DurableSpool(tmp_path / "spool.db") as spool:
        spool.put("fall", '{"fall": true}')
        before = spool.pending()
        with pytest.raises(SpoolCapacityError):
            spool.put("oversized", "x" * spool.max_bytes)
        assert spool.pending() == before

"""The one property that matters: an item survives a restart until acked or expired."""

from mantau_core.buffer import DurableSpool


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

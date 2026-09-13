import asyncio

from mantau_core.notify.delivery import AckService
from mantau_core.notify.escalation import EscalationChain, EscalationPolicy
from mantau_core.notify.recipients import EmergencyContact

ANAK = EmergencyContact(contact_id="anak", name="Budi", phone="+62-1", relation="Anak", priority=1)
CUCU = EmergencyContact(contact_id="cucu", name="Sari", phone="+62-2", relation="Cucu", priority=2)
TETANGGA = EmergencyContact(contact_id="tetangga", name="Wati", phone="+62-3", relation="Tetangga", priority=3)


def test_chain_orders_by_priority_regardless_of_input_order():
    chain = EscalationChain(contacts=[CUCU, TETANGGA, ANAK])
    assert [c.contact_id for c in chain.ordered()] == ["anak", "cucu", "tetangga"]


def test_chain_next_after_none_returns_the_first_contact():
    chain = EscalationChain(contacts=[ANAK, CUCU])
    assert chain.next_after(None).contact_id == "anak"


def test_chain_next_after_last_contact_returns_none():
    chain = EscalationChain(contacts=[ANAK, CUCU])
    assert chain.next_after("cucu") is None


def test_chain_empty_returns_none():
    chain = EscalationChain(contacts=[])
    assert chain.next_after(None) is None


def test_policy_stops_escalating_once_acked():
    chain = EscalationChain(contacts=[ANAK, CUCU, TETANGGA])
    ack_service = AckService()
    notified = []

    async def notify_contact(contact):
        notified.append(contact.contact_id)

    calls = {"n": 0}

    async def fake_sleep(seconds):
        calls["n"] += 1
        if calls["n"] == 1:
            ack_service.ack("ev-1", member_id="anak")  # acked during the first wait

    policy = EscalationPolicy(window_s=60.0)
    result = asyncio.run(policy.run(
        event_id="ev-1", chain=chain, ack_service=ack_service,
        notify_contact=notify_contact, sleep=fake_sleep,
    ))

    assert notified == ["anak"]
    assert result.contact_id == "anak"


def test_policy_walks_the_whole_chain_if_nobody_acks():
    chain = EscalationChain(contacts=[ANAK, CUCU, TETANGGA])
    ack_service = AckService()
    notified = []

    async def notify_contact(contact):
        notified.append(contact.contact_id)

    async def fake_sleep(seconds):
        pass  # nobody ever acks

    policy = EscalationPolicy(window_s=60.0)
    result = asyncio.run(policy.run(
        event_id="ev-1", chain=chain, ack_service=ack_service,
        notify_contact=notify_contact, sleep=fake_sleep,
    ))

    assert notified == ["anak", "cucu", "tetangga"]
    assert result.contact_id == "tetangga"


def test_policy_notifies_nobody_if_already_acked():
    chain = EscalationChain(contacts=[ANAK, CUCU])
    ack_service = AckService()
    ack_service.ack("ev-1", member_id="someone")
    notified = []

    async def notify_contact(contact):
        notified.append(contact.contact_id)

    async def fake_sleep(seconds):
        pass

    policy = EscalationPolicy(window_s=60.0)
    result = asyncio.run(policy.run(
        event_id="ev-1", chain=chain, ack_service=ack_service,
        notify_contact=notify_contact, sleep=fake_sleep,
    ))

    assert notified == []
    assert result is None


def test_policy_empty_chain_returns_none_immediately():
    chain = EscalationChain(contacts=[])
    ack_service = AckService()
    notified = []

    async def notify_contact(contact):
        notified.append(contact.contact_id)

    async def fake_sleep(seconds):
        pass

    policy = EscalationPolicy()
    result = asyncio.run(policy.run(
        event_id="ev-1", chain=chain, ack_service=ack_service,
        notify_contact=notify_contact, sleep=fake_sleep,
    ))

    assert notified == []
    assert result is None

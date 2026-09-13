"""No ack within the window -> notify the next contact in the chain.

This is what turns "contacted in sequence when a notification goes
unanswered" from UI copy into something the backend actually enforces. The
walk only owns timing; `notify_contact` is the caller's own send logic
(push to that specific person, SMS, WhatsApp — whatever channel is wired up
for emergency contacts) so this module stays channel-agnostic.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from mantau_core.notify.delivery.ack import AckService
from mantau_core.notify.recipients import EmergencyContact

from .chain import EscalationChain


@dataclass
class EscalationPolicy:
    window_s: float = 60.0  # how long to wait for an ack before moving on

    async def run(
        self,
        *,
        event_id: str,
        chain: EscalationChain,
        ack_service: AckService,
        notify_contact: Callable[[EmergencyContact], Awaitable[None]],
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> EmergencyContact | None:
        """Walk the chain until someone acks or it runs out.

        Returns the last contact notified (None if the chain was empty or
        already acked before the first notify) — useful for tests and logs,
        not required by callers that only care whether anyone responded.
        """
        current: EmergencyContact | None = None
        while True:
            if ack_service.is_acked(event_id):
                return current
            nxt = chain.next_after(current.contact_id if current else None)
            if nxt is None:
                return current
            await notify_contact(nxt)
            current = nxt
            await sleep(self.window_s)

"""Dev sink — prints instead of sending. No network, no config, always
"succeeds" — for local runs and for wiring tests that care about the fanout
logic, not about a real channel.
"""

from __future__ import annotations

from mantau_core.notify.alert import Alert
from mantau_core.notify.protocol import Delivery, DeliveryStatus


class ConsoleChannel:
    async def send(self, alert: Alert, target: str) -> Delivery:
        print(f"[notify] -> {target}: {alert.title} :: {alert.body}")
        return Delivery(event_id=alert.event_id, status=DeliveryStatus.DELIVERED, detail=target)

    async def close(self) -> None:
        pass

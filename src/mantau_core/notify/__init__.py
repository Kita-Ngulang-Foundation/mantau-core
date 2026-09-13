"""Event -> alert -> every configured channel -> tracked delivery -> escalation.

Push (`channels.push`) is the channel built to completion; Telegram
(`channels.telegram`) is explicitly temporary — see that module's docstring
before extending it. Submodules, not re-exported here to keep this file
light: `channels.push`, `channels.telegram`, `channels.console`, `delivery`,
`escalation`, `templates`.
"""

from .alert import Alert
from .fanout import ChannelBinding, Fanout, PushBinding, TelegramBinding
from .protocol import Delivery, DeliveryStatus, Notifier
from .recipients import EmergencyContact, RecipientResolver

__all__ = [
    "Alert",
    "Delivery",
    "DeliveryStatus",
    "Notifier",
    "EmergencyContact",
    "RecipientResolver",
    "Fanout",
    "ChannelBinding",
    "PushBinding",
    "TelegramBinding",
]

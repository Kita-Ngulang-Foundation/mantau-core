"""Camera -> who to tell. Two separate audiences, on purpose:

`DeviceToken`s are app installs — the primary push audience, resolved by
`devices_for_camera`. `EmergencyContact`s (name/phone/relation, mirroring
`mantau-app`'s existing model exactly) are the escalation chain for when
nobody acks the push — they don't need the app installed at all, which is
exactly why they're a separate list rather than another kind of device.

`RecipientResolver` is a Protocol: each backend implements it against its
own SQLite store. Nothing in this package ever opens a database connection.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from .channels.push.tokens import DeviceToken


class EmergencyContact(BaseModel):
    contact_id: str
    name: str
    phone: str
    relation: str
    priority: int  # lower = contacted first; ties broken by insertion order


class RecipientResolver(Protocol):
    def devices_for_camera(self, camera_id: str) -> list[DeviceToken]:
        ...

    def emergency_contacts_for_camera(self, camera_id: str) -> list[EmergencyContact]:
        ...

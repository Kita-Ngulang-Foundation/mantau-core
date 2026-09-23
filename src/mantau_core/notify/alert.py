"""What actually gets sent — a FallEvent plus the human-facing context a
channel needs (which camera, what to say, where tapping it should go).

Built once per event via `Alert.from_event`, then handed unchanged to every
channel/target pair in the fanout — a channel never re-derives copy or the
deep link, it just delivers this.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from mantau_core.contracts import EventKind, FallEvent, Severity


class Alert(BaseModel):
    event_id: str
    camera_id: str
    camera_name: str
    # Lets the app pick icon/copy per detection without parsing the title.
    kind: EventKind = EventKind.FALL
    severity: Severity
    title: str
    body: str
    deep_link: str      # e.g. "mantau://events/{event_id}" -> the app's existing deepLinkEventId
    collapse_key: str    # a repeat send for the same event replaces, never stacks
    occurred_at: datetime

    @classmethod
    def from_event(cls, event: FallEvent, *, camera_name: str, title: str, body: str) -> "Alert":
        return cls(
            event_id=event.event_id,
            camera_id=event.camera_id,
            camera_name=camera_name,
            kind=event.kind,
            severity=event.severity,
            title=title,
            body=body,
            deep_link=f"mantau://events/{event.event_id}",
            collapse_key=f"{event.kind.value}:{event.event_id}",
            occurred_at=event.occurred_at,
        )

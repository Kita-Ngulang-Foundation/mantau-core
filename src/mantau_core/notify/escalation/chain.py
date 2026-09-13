"""An ordered walk through a household's emergency contacts.

Mirrors the app's own model exactly — `EmergencyContact` there is already
described as "kontak yang dihubungi berurutan" (contacted in sequence).
`priority` is what makes that order explicit and backend-enforceable instead
of just a list's incidental ordering.
"""

from __future__ import annotations

from dataclasses import dataclass

from mantau_core.notify.recipients import EmergencyContact


@dataclass
class EscalationChain:
    contacts: list[EmergencyContact]

    def ordered(self) -> list[EmergencyContact]:
        return sorted(self.contacts, key=lambda c: c.priority)

    def next_after(self, contact_id: str | None) -> EmergencyContact | None:
        """`contact_id=None` means "start of chain". Returns None once the
        chain runs out — the caller decides what "nobody responded" means."""
        ordered = self.ordered()
        if not ordered:
            return None
        if contact_id is None:
            return ordered[0]
        ids = [c.contact_id for c in ordered]
        try:
            idx = ids.index(contact_id)
        except ValueError:
            return ordered[0]
        return ordered[idx + 1] if idx + 1 < len(ordered) else None

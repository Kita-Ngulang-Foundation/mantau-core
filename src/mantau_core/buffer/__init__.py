"""Hold recent events through a brief outage instead of silently losing them.

This buffers *serialized events/envelopes* (small, JSON, KB-sized) — not raw
video frames. A few minutes of frames would be gigabytes; a few minutes of
fall events is a handful of rows. If frame-level replay ever becomes a real
requirement, that is a deliberately separate, larger piece of work.
"""

from .spool import DurableSpool, SpoolItem

__all__ = ["DurableSpool", "SpoolItem"]

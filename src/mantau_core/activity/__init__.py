"""From "who is where, doing what" to anomaly events.

A perception model (pose estimation) turns frames into `FrameObservation`s.
`ActivityEngine` feeds each observation to a set of `ActivityRule`s -- one
per feature (prolonged stillness, nocturnal movement, bathroom duration) --
and returns the events they raise. Falls come straight from the detector;
everything slower than a fall is a rule here.

Rules are pure, deterministic state machines over observations and an
injected clock, so they are tested with synthetic observation sequences and
behave identically on every agent platform and in cloud inference.
"""

from .engine import ActivityEngine, ActivityRule
from .clock import in_window, local_time
from .geometry import point_in_polygon, zone_at
from .observations import FrameObservation, PersonObservation, Posture, Perception

__all__ = [
    "ActivityEngine",
    "ActivityRule",
    "in_window",
    "local_time",
    "FrameObservation",
    "Perception",
    "PersonObservation",
    "Posture",
    "point_in_polygon",
    "zone_at",
]

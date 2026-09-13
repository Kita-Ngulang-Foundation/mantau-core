"""mantau_core — shared vocabulary for both Mantau backend scenarios.

Installed by mantau-backend-rtsp and mantau-backend-localdevice so the two
prototypes differ only where they are supposed to differ (how a frame reaches
the detector), not in how a fall becomes a notification.

Submodules are independent — import only what you need:

    contracts   event/camera/envelope shapes, reachability error taxonomy
    detection   Detector protocol + NullDetector + the mantau-ai adapter
    notify      alerts, push/telegram channels, delivery tracking, escalation
    buffer      durable spool for holding events through an outage
    resilience  backoff + a supervised-restart task runner
    telemetry   per-event latency trace + simple counters
    config      a pydantic-settings base both backends extend
"""

__version__ = "0.1.0"

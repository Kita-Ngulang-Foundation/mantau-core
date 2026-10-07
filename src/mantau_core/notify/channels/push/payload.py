"""Build the FCM HTTP v1 message body — shaped to survive a sleeping phone,
not just to be valid JSON.

`android.priority: high` bypasses Doze/App Standby; `apns-priority: 10` is
the iOS equivalent. `channel_id` targets the notification channel the app
already creates at max importance with the alarm category
(`mantau_alerts` — see mantau-app's `NotificationService`), so this payload
needs no app-side changes to ring through. The collapse key means a second
push for the same fall replaces the first instead of stacking two alerts for
one event.

INFO alerts (the night summary) are quiet: normal priority on both
platforms, no sound, and the app's default-importance `mantau_info` channel,
because on Android the channel, not the message, decides whether it rings.
"""

from __future__ import annotations

from mantau_core.contracts import Severity
from mantau_core.notify.alert import Alert

ANDROID_CHANNEL_ID = "mantau_alerts"  # must match the channel the app creates
ANDROID_INFO_CHANNEL_ID = "mantau_info"  # the app's quiet channel for INFO alerts


def build_fcm_message(*, token: str, alert: Alert) -> dict:
    # APNs collapse ids are capped at 64 bytes by Apple; truncate defensively.
    apns_collapse_id = alert.collapse_key[:64]
    quiet = alert.severity is Severity.INFO
    aps = {"category": "MANTAU_ALERT"} if quiet else {"sound": "default",
                                                      "category": "MANTAU_ALERT"}
    return {
        "message": {
            "token": token,
            "notification": {"title": alert.title, "body": alert.body},
            "data": {
                **({"household_id": alert.household_id} if alert.household_id else {}),
                "event_id": alert.event_id,
                "camera_id": alert.camera_id,
                "deep_link": alert.deep_link,
                "severity": alert.severity.value,
                "kind": alert.kind.value,
            },
            "android": {
                "priority": "normal" if quiet else "high",
                "notification": {
                    "channel_id": ANDROID_INFO_CHANNEL_ID if quiet else ANDROID_CHANNEL_ID,
                    "tag": alert.collapse_key,
                },
            },
            "apns": {
                "headers": {
                    "apns-priority": "5" if quiet else "10",
                    "apns-collapse-id": apns_collapse_id,
                },
                "payload": {
                    "aps": aps,
                },
            },
        }
    }

"""Build the FCM HTTP v1 message body — shaped to survive a sleeping phone,
not just to be valid JSON.

`android.priority: high` bypasses Doze/App Standby; `apns-priority: 10` is
the iOS equivalent. `channel_id` targets the notification channel the app
already creates at max importance with the alarm category
(`mantau_alerts` — see mantau-app's `NotificationService`), so this payload
needs no app-side changes to ring through. The collapse key means a second
push for the same fall replaces the first instead of stacking two alerts for
one event.
"""

from __future__ import annotations

from mantau_core.notify.alert import Alert

ANDROID_CHANNEL_ID = "mantau_alerts"  # must match the channel the app creates


def build_fcm_message(*, token: str, alert: Alert) -> dict:
    # APNs collapse ids are capped at 64 bytes by Apple; truncate defensively.
    apns_collapse_id = alert.collapse_key[:64]
    return {
        "message": {
            "token": token,
            "notification": {"title": alert.title, "body": alert.body},
            "data": {
                "event_id": alert.event_id,
                "camera_id": alert.camera_id,
                "deep_link": alert.deep_link,
                "severity": alert.severity.value,
                "kind": alert.kind.value,
            },
            "android": {
                "priority": "high",
                "notification": {
                    "channel_id": ANDROID_CHANNEL_ID,
                    "tag": alert.collapse_key,
                },
            },
            "apns": {
                "headers": {
                    "apns-priority": "10",
                    "apns-collapse-id": apns_collapse_id,
                },
                "payload": {
                    "aps": {"sound": "default", "category": "MANTAU_ALERT"},
                },
            },
        }
    }

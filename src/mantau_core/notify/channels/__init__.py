"""Channel implementations of the `Notifier` protocol.

Import the specific one you need (`from mantau_core.notify.channels.push import
FCMPushChannel`, `from mantau_core.notify.channels.telegram import
TelegramChannel`) rather than from this package directly — it keeps
`google-auth` (push-only) and `httpx` usage explicit at the call site.
"""

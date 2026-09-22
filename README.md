# mantau-core

Shared contracts, notification, resilience and telemetry for both Mantau
backend scenarios (`mantau-backend-rtsp` and `mantau-backend-localdevice`).
Installed by each as a git dependency, pinned to a commit:

```
pip install "mantau-core @ git+https://github.com/<org>/mantau-core.git@<sha>"
```

The point of this package: the two backends should differ **only** in how a
frame reaches the detector (direct RTSP pull vs. agent + tunnel). Everything
after "a fall was detected" — the event shape, who gets told, how, and how
that's measured — lives here once, so the comparison between the two
scenarios is honest.

## Modules

| Module | What it owns |
|---|---|
| `contracts` | `FallEvent`, `CameraRef`, `Envelope` (signed agent→server wire format), the reachability error taxonomy. The vocabulary — extend here first, never redeclare locally. |
| `detection` | `Detector` protocol, `NullDetector` (always-empty, or fires on a fixed cadence for wiring tests), `MediapipeDetector` — **the only module that imports `mantau.*`** (the CV package), gated behind the `detection` extra. |
| `notify` | `Fanout` → `Alert` → channels (`push` built to completion, `telegram` explicitly temporary, `console` for dev) → `DeliveryTracker` → `AckService` → `EscalationChain`/`EscalationPolicy`. |
| `buffer` | `DurableSpool` — a SQLite-backed, TTL-evicting queue so a brief outage doesn't silently lose an event. |
| `resilience` | `BackoffPolicy` (full-jitter exponential backoff) and `Supervisor` (restart a task with backoff, bounded, observable). |
| `telemetry` | `LatencyTrace` (`captured → detected → queued → sent → delivered → acked`, the number the whole project is judged on) and a tiny `MetricsRegistry`. |
| `config` | `CoreSettings` — a `pydantic-settings` base each backend subclasses with its own fields. |

## Control-plane contract v1

`mantau_core.contracts.control` is the additive v1 vocabulary for claims,
capability/status reports, discovery, camera-request metadata, requested and
effective inference modes, and durable command receipts/results. Existing
`Envelope`, event, heartbeat, camera, and error models are unchanged.

Language-neutral golden JSON lives under
`src/mantau_core/contracts/fixtures/v1/` and is included in built packages.
Python tests validate exact round trips today; the same files are intended as
Kotlin serialization fixtures later. Fixtures and all normal status/result
models intentionally have no camera password, enrollment secret, private key,
credential object, or raw RTSP URL.

Compatibility/rollback: deploy this package before the new server/agent code.
Old readers continue using the unchanged contracts and ignore the new module.
Rolling back consumers needs no data conversion because schema v1 is additive;
do not delete or rename old contracts during the mixed-version window.

## Install

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Optional extras:
- `.[push]` — pulls in `google-auth`, needed only to actually send FCM push (`ServiceAccountCredentials`). Importing `mantau_core.notify` never requires it.
- `.[detection]` — pulls in `mantau` (the CV package) at a pinned SHA, needed only to construct `MediapipeDetector`.

## Test

```powershell
.venv\Scripts\python.exe -m pytest tests/ -q
```

All tests run offline — HTTP channels (FCM, Telegram) are tested against
`httpx.MockTransport`, never a real network call.

## The one file that touches `mantau-ai`

`src/mantau_core/detection/mediapipe_adapter.py` is the **only** place in
this entire package allowed to `import mantau.*`. It currently raises a
clear `ImportError` on construction, because `mantau-ai` doesn't yet expose
a streaming entrypoint — `mantau.api.streaming.StreamingDetector`, taking
frames in and returning `FallEvent`s out. Until that ships, both backends
build and test against `NullDetector`, which satisfies the same `Detector`
protocol.

## Push vs. Telegram

Push (FCM, HTTP v1, OAuth2 service-account auth) is the real notification
channel and is built to completion: token lifecycle, a payload shaped to
survive Doze/App Standby, delivery tracking through to a device **ack**, and
escalation to the next emergency contact if nobody acks in time.

Telegram is explicitly temporary — demo insurance in case FCM misbehaves on
demo day, and a useful control (if latency holds on Telegram but not push,
the delay is in delivery, not detection). See the docstring at the top of
`notify/channels/telegram.py` before extending it; the intent is to delete
that file once push is proven in the field, not to build on top of it.

## What each backend still owns

This package defines protocols (`Detector`, `Notifier`, `TokenStore`,
`RecipientResolver`) rather than storage. Each backend repo implements these
against its own SQLite store, its own FastAPI routes, and its own
Docker Compose — `mantau-core` never opens a database connection or a
socket beyond what `httpx` needs to actually send a notification.

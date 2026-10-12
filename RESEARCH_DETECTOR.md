# Per-camera fall configuration

The server selects the fall model and confirmation policy from each camera's
`DetectionSettings.fall`. Defaults are `model="research"`, `tau_loose=0.92`,
`tau_high=0.98`, `confirm_loose_s=15`, `confirm_high_s=5`, `down_share=0.6`.
Set `model="s1b"` to restore the existing detector for a camera. Optional entry
guards use `min_track_age_s=0` and `max_edge_frac=1` (disabled defaults).
`tau_high >= tau_loose` and `confirm_high_s <= confirm_loose_s` are validated.

The adapter remains the sole core import site for `mantau.*`; it verifies the
packaged model hashes and translates candidate updates into existing events.
Direct adapter callers select research via `{"fall_model":"research",
"fall_confirmation":{...}}`; its existing default remains S1b for compatibility.
The server explicitly derives research selection from camera settings.
The camera's bed and seating zones reach the research confirm step. A
candidate that would confirm while the person rests in such a zone (hip
midpoint inside it for `down_share` of the down frames) resolves as outcome 5:
INFO in history with the zone's `zone_id`, no alert.
Activity rules, including the 30 s floor backup, retain their existing logic.

Candidate event ids and capture times remain stable through confirmation.
History uses INFO for pending/recovered candidates and CRITICAL on confirmation.
Signals record probability, down fraction, tier, outcome, geometry and elapsed
time. `advance(ts_ms)` provides timer expiration when uploads stop.

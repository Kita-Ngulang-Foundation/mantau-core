"""A registered camera and how to reach its RTSP stream.

Credentials are kept separate from the URL (a `SecretStr`, never logged) even
though RTSP conventionally embeds them (`rtsp://user:pass@host/path`) — the
composed, credential-bearing URL is built once, right where a stream is
opened, via `CameraRef.stream_url()`, and discarded immediately after.
"""

from __future__ import annotations

from enum import Enum
from urllib.parse import quote

from pydantic import BaseModel, SecretStr


class StreamProfile(str, Enum):
    """Which RTSP track to request.

    Fall detection needs motion and a bounding box, not resolution — the
    brief is explicit that the agent should request the camera's low-bitrate
    SUB stream, never MAIN, to keep LAN/uplink bandwidth low.
    """

    MAIN = "main"
    SUB = "sub"


class Credentials(BaseModel):
    username: str
    password: SecretStr

    def __repr__(self) -> str:  # never leak the password via logging/repr
        return f"Credentials(username={self.username!r}, password=SecretStr('**********'))"


class CameraRef(BaseModel):
    """A camera as the system knows it — independent of which scenario reaches it."""

    camera_id: str
    name: str
    host: str
    port: int = 554
    # Per-profile RTSP path, e.g. {"main": "/stream1", "sub": "/stream2"}.
    # A camera without a real sub-stream may map both profiles to the same path.
    paths: dict[StreamProfile, str] = {StreamProfile.MAIN: "/stream1"}
    credentials: Credentials | None = None
    # Set when found via ONVIF WS-Discovery rather than typed in by a person.
    onvif_endpoint: str | None = None

    def stream_url(self, profile: StreamProfile = StreamProfile.SUB) -> str:
        """Build the full authenticated RTSP URL for one profile.

        Falls back to MAIN if this camera has no distinct SUB path configured
        — better a heavier stream than none. Call this right at the point of
        opening the connection; never persist or log the result.
        """
        path = self.paths.get(profile) or self.paths.get(StreamProfile.MAIN)
        if path is None:
            raise ValueError(f"camera {self.camera_id!r} has no RTSP path configured")
        auth = ""
        if self.credentials is not None:
            user = quote(self.credentials.username, safe="")
            pw = quote(self.credentials.password.get_secret_value(), safe="")
            auth = f"{user}:{pw}@"
        return f"rtsp://{auth}{self.host}:{self.port}{path}"

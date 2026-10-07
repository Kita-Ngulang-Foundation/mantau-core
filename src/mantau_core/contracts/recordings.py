"""Metadata only: recordings stay on agents and family phones."""
from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentRecording(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    size_bytes: int = Field(gt=0, le=20 * 1024 * 1024)
    captured_at_ms: int = Field(ge=0)


class AgentRecordingsSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recordings: list[AgentRecording] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def unique_events(self):
        if len({clip.event_id for clip in self.recordings}) != len(self.recordings):
            raise ValueError("duplicate recording identifiers")
        return self

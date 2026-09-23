"""Bounded caption payload accepted from either fetch environment."""
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Cue(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    start: float = Field(ge=0, le=86400)
    end: float = Field(ge=0, le=86400)
    text: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def ordered(self):
        if self.end < self.start or not self.text.strip() or "\x00" in self.text:
            raise ValueError("Invalid cue")
        return self


class Transcript(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: Optional[str] = Field(default=None, max_length=35, pattern=r"^[A-Za-z0-9-]+$")
    is_generated: bool = True
    cues: list[Cue] = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def bounded(self):
        if sum(len(c.text.encode("utf-8")) for c in self.cues) > 1_000_000:
            raise ValueError("Caption text too large")
        if any(b.start < a.start for a, b in zip(self.cues, self.cues[1:])):
            raise ValueError("Cues must be ordered")
        return self


class Completion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    video_id: str = Field(pattern=r"^[A-Za-z0-9_-]{11}$")
    lease_token: str = Field(min_length=43, max_length=43)
    transcript: Optional[Transcript] = None
    error: Optional[Literal["fetch_failed", "blocked", "no_captions", "unavailable", "timeout"]] = None

    @model_validator(mode="after")
    def result_required(self):
        if (self.transcript is None) == (self.error is None):
            raise ValueError("Exactly one result required")
        return self

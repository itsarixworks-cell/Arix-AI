from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SessionStart(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["session.start"]
    api_key: str = Field(alias="apiKey", default="", max_length=512)
    model: str = Field(default="gemini-3.1-flash-live-preview", min_length=3, max_length=128)
    voice: str = Field(default="Kore", min_length=2, max_length=32)
    system_instruction: str = Field(
        alias="systemInstruction",
        default="You are Arix, a helpful voice-first desktop assistant.",
        max_length=8000,
    )


class TextInput(BaseModel):
    type: Literal["text"]
    text: str = Field(min_length=1, max_length=32000)


ClientMessage = SessionStart | TextInput

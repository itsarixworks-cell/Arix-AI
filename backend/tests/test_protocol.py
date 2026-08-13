import pytest
from pydantic import ValidationError

from backend.app.core.protocol import SessionStart, TextInput


def test_session_start_accepts_frontend_aliases() -> None:
    value = SessionStart.model_validate({
        "type": "session.start",
        "apiKey": "test-key",
        "model": "gemini-live-test",
        "voice": "Kore",
        "systemInstruction": "Be useful.",
    })
    assert value.api_key == "test-key"
    assert value.system_instruction == "Be useful."


def test_empty_text_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TextInput(type="text", text="")

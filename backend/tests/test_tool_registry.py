import json
from pathlib import Path

import pytest

from backend.app.memory.runtime import create_memory_runtime
from backend.app.tools.registry import ToolDefinition, ToolRegistry
from backend.app.tools.safety import ConfirmationRequired


@pytest.mark.asyncio
async def test_memory_tools_are_declared_and_executable(tmp_path: Path) -> None:
    runtime = await create_memory_runtime(tmp_path)
    expected = {
        "save_memory", "request_memory", "open_app", "web_search", "weather_report",
        "reminder", "computer_settings", "computer_control", "gesture_control", "file_controller",
        "browser_control", "desktop_control", "send_message", "youtube_video",
        "screen_process", "smart_home_control", "game_updater", "flight_finder",
        "file_processor", "presentation_builder", "spreadsheet_builder", "word_document",
        "pdf_document", "agent_task", "shutdown_arix",
    }
    assert expected == set(runtime.tools.names)
    declarations = runtime.tools.declarations()
    assert len(declarations) == 1
    result = await runtime.tools.execute("save_memory", {"text": "User likes quiet mornings."})
    assert result["ok"] is True
    assert "duration_ms" in result
    assert "quiet mornings" in await runtime.service.scratchpad.read()
    audit = [json.loads(line) for line in (tmp_path / "tool_audit.jsonl").read_text().splitlines()]
    assert audit[-1]["tool"] == "save_memory"
    assert audit[-1]["argument_keys"] == ["text"]
    assert audit[-1]["ok"] is True


@pytest.mark.asyncio
async def test_registry_returns_structured_errors_and_audits_without_values(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    registry = ToolRegistry(audit_path=audit_path)

    async def guarded(secret: str) -> dict[str, object]:
        raise ConfirmationRequired(f"Confirmation required for {len(secret)} characters")

    registry.register(ToolDefinition(
        name="guarded",
        description="Test tool",
        parameters={"type": "object"},
        handler=guarded,
    ))
    result = await registry.execute("guarded", {"secret": "do-not-log"})
    assert result["ok"] is False
    assert result["error_code"] == "confirmation_required"
    assert result["tool"] == "guarded"
    assert isinstance(result["duration_ms"], int)

    unknown = await registry.execute("missing", {})
    assert unknown["error_code"] == "unknown_tool"
    records = [json.loads(line) for line in audit_path.read_text().splitlines()]
    assert records[0]["argument_keys"] == ["secret"]
    assert "do-not-log" not in audit_path.read_text()

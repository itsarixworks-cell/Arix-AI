from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.app.tools.document_tools import (
    _agent_task_sync,
    _pdf_document_sync,
    _presentation_builder_sync,
    _spreadsheet_builder_sync,
    _word_document_sync,
    register_document_tools,
    shutdown_arix,
)
from backend.app.tools.registry import ToolRegistry
from backend.app.tools.safety import ConfirmationRequired


def test_document_tools_register() -> None:
    registry = ToolRegistry()
    register_document_tools(registry)
    assert registry.names == (
        "presentation_builder", "spreadsheet_builder", "word_document", "pdf_document",
        "agent_task", "shutdown_arix",
    )
    assert registry.declarations()


def test_word_document_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "report.docx"

    def safe_path(raw: str):
        return Path(raw)

    with patch("backend.app.tools.document_tools.resolve_user_path", side_effect=safe_path):
        result = _word_document_sync(
            "Arix Report",
            [{"heading": "Summary", "text": "All executable tools are bounded.", "bullets": ["Safe", "Tested"]}],
            str(target),
            "Arix AI",
            False,
            False,
        )
    assert result["created"] is True
    assert target.exists()
    assert target.stat().st_size > 0


def test_presentation_spreadsheet_and_pdf_builders(tmp_path: Path) -> None:
    def safe_path(raw: str):
        return Path(raw)

    with patch("backend.app.tools.document_tools.resolve_user_path", side_effect=safe_path):
        presentation = _presentation_builder_sync(
            "Roadmap", [{"title": "Arix", "bullets": ["Safe tools", "Structured results"]}],
            str(tmp_path / "roadmap.pptx"), False, False,
        )
        spreadsheet = _spreadsheet_builder_sync(
            "Inventory", [{"name": "Tools", "rows": [["Name", "Status"], ["Arix", "Ready"]]}],
            str(tmp_path / "inventory.xlsx"), False, False,
        )
        pdf = _pdf_document_sync(
            "Summary", [{"heading": "Tools", "text": "Arix uses strict schemas."}],
            str(tmp_path / "summary.pdf"), "Arix AI", False, False,
        )
    for result in (presentation, spreadsheet, pdf):
        assert result["created"] is True
        assert Path(result["path"]).stat().st_size > 0


def test_agent_task_lifecycle_is_structured(tmp_path: Path) -> None:
    store = tmp_path / "tasks.json"
    with patch("backend.app.tools.document_tools._task_store", return_value=store):
        created = _agent_task_sync("create", "", "Review tests", "Run checks", ["pytest"], "pending", False)
        task_id = created["task"]["id"]
        updated = _agent_task_sync("update", task_id, "", "", None, "completed", False)
        assert updated["task"]["status"] == "completed"
        with pytest.raises(ConfirmationRequired):
            _agent_task_sync("delete", task_id, "", "", None, "pending", False)
        deleted = _agent_task_sync("delete", task_id, "", "", None, "pending", True)
    assert deleted["deleted"] is True


@pytest.mark.asyncio
async def test_shutdown_requires_confirmation_and_schedules_timer() -> None:
    with pytest.raises(ConfirmationRequired):
        await shutdown_arix(False)
    timer = MagicMock()
    with patch("backend.app.tools.document_tools.threading.Timer", return_value=timer) as factory:
        result = await shutdown_arix(True, 2)
    assert result["shutdown_scheduled"] is True
    factory.assert_called_once()
    timer.start.assert_called_once()

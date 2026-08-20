from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.app.tools.registry import ToolRegistry
from backend.app.tools.safety import ConfirmationRequired
from backend.app.tools.workspace_tools import (
    _BrowserRuntime,
    _file_controller_sync,
    _safe_browser_url,
    register_workspace_tools,
)


def test_workspace_tools_register() -> None:
    registry = ToolRegistry()
    register_workspace_tools(registry)
    assert registry.names == ("file_controller", "browser_control", "desktop_control")


@pytest.mark.asyncio
async def test_file_creation_through_registry_is_verified(tmp_path: Path) -> None:
    target = tmp_path / "created.txt"
    registry = ToolRegistry()
    register_workspace_tools(registry)

    def safe_path(raw: str, must_exist: bool = False):
        path = Path(raw)
        if must_exist and not path.exists():
            raise FileNotFoundError(raw)
        return path

    with patch("backend.app.tools.workspace_tools.resolve_user_path", side_effect=safe_path):
        result = await registry.execute("file_controller", {
            "action": "create_file",
            "path": str(target),
            "content": "verified",
        })
    assert result["ok"] is True
    output = result["result"]
    assert output["completed"] is True
    assert output["exists"] is True
    assert output["bytes"] == 8
    assert target.read_text(encoding="utf-8") == "verified"


def test_file_read_and_write_confirmation(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("old", encoding="utf-8")

    def safe_path(raw: str, must_exist: bool = False):
        path = Path(raw)
        if must_exist and not path.exists():
            raise FileNotFoundError(raw)
        return path

    with patch("backend.app.tools.workspace_tools.resolve_user_path", side_effect=safe_path):
        result = _file_controller_sync("read", str(source), "", "", "", False, False)
        assert result["content"] == "old"
        with pytest.raises(ConfirmationRequired):
            _file_controller_sync("write", str(source), "", "new", "", False, False)
        changed = _file_controller_sync("write", str(source), "", "new", "", True, False)
    assert changed["bytes_written"] == 3
    assert changed["completed"] is True
    assert changed["exists"] is True
    assert changed["bytes"] == 3
    assert source.read_text(encoding="utf-8") == "new"


def test_folder_organization_by_date_requires_confirmation(tmp_path: Path) -> None:
    source = tmp_path / "Downloads"
    source.mkdir()
    (source / "report.txt").write_text("ready", encoding="utf-8")

    with patch("backend.app.tools.workspace_tools.resolve_user_path", return_value=source):
        with pytest.raises(ConfirmationRequired):
            _file_controller_sync("organize", str(source), "", "", "", False, False, "date")
        result = _file_controller_sync("organize", str(source), "", "", "", True, False, "date")
    assert result["completed"] is True
    assert result["count"] == 1
    assert Path(result["moved"][0]["to"]).exists()


def test_file_delete_uses_recycle_bin(tmp_path: Path) -> None:
    source = tmp_path / "discard.txt"
    source.write_text("x", encoding="utf-8")
    trash = MagicMock()
    trash.send2trash = MagicMock()
    with (
        patch("backend.app.tools.workspace_tools.resolve_user_path", return_value=source),
        patch("backend.app.tools.workspace_tools.require_optional_dependency", return_value=trash),
    ):
        with pytest.raises(ConfirmationRequired):
            _file_controller_sync("delete", str(source), "", "", "", False, False)
        result = _file_controller_sync("delete", str(source), "", "", "", True, False)
    assert result["recycled"] is True
    trash.send2trash.assert_called_once_with(str(source))


def test_browser_url_blocks_internal_and_file_schemes() -> None:
    assert _safe_browser_url("example.com") == "https://example.com"
    with pytest.raises(ValueError, match="HTTP and HTTPS"):
        _safe_browser_url("file:///etc/passwd")
    with pytest.raises(ValueError, match="blocked"):
        _safe_browser_url("http://localhost:3000")


def test_browser_form_fill_reports_completed_fields_without_values() -> None:
    runtime = _BrowserRuntime()
    page = MagicMock()
    page.url = "https://example.com/form"
    page.title.return_value = "Form"
    with patch.object(runtime, "_ensure", return_value=page):
        result = runtime.execute(
            "fill_form", "", "", "", "", "", 0, 0, False, False,
            [{"selector": "#name", "value": "Private Name"}],
        )
    assert result["completed"] is True
    assert result["fields_filled"] == 1
    assert "Private Name" not in str(result)
    page.locator.return_value.first.fill.assert_called_once_with("Private Name")
    runtime.executor.shutdown(wait=False, cancel_futures=True)


def test_browser_consequential_click_requires_confirmation() -> None:
    runtime = _BrowserRuntime()
    page = MagicMock()
    page.url = "https://example.com/cart"
    page.title.return_value = "Cart"
    with patch.object(runtime, "_ensure", return_value=page):
        with pytest.raises(ConfirmationRequired):
            runtime.execute("click", "", "", "button.buy", "", "", 0, 0, False, True)
        result = runtime.execute("click", "", "", "button.buy", "", "", 0, 0, True, True)
    assert result["completed"] is True
    page.locator.return_value.first.click.assert_called_once()
    runtime.executor.shutdown(wait=False, cancel_futures=True)

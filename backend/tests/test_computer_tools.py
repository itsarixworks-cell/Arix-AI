from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from backend.app.tools.computer_tools import (
    _computer_control_sync,
    _computer_settings_sync,
    _create_reminder,
    register_computer_tools,
)
from backend.app.tools.registry import ToolRegistry
from backend.app.tools.safety import ConfirmationRequired


def test_computer_tools_register() -> None:
    registry = ToolRegistry()
    register_computer_tools(registry)
    assert registry.names == ("reminder", "computer_settings", "computer_control")


def test_reminder_uses_schtasks_without_shell(tmp_path) -> None:
    future = datetime.now() + timedelta(days=1)
    with (
        patch("backend.app.tools.computer_tools.require_platform", return_value="Windows"),
        patch("backend.app.tools.computer_tools._reminder_directory", return_value=tmp_path),
        patch("backend.app.tools.computer_tools.run_command") as command,
    ):
        result = _create_reminder(
            future.strftime("%Y-%m-%d"), future.strftime("%H:%M"), "Review Arix's tests"
        )
    assert result["created"] is True
    args = command.call_args.args[0]
    assert args[0] == "schtasks.exe"
    assert "/Create" in args
    script = next(tmp_path.glob("*.ps1")).read_text(encoding="utf-8")
    assert "Review Arix''s tests" in script


def test_shutdown_requires_confirmation_before_command() -> None:
    with (
        patch("backend.app.tools.computer_tools.require_platform", return_value="Windows"),
        patch("backend.app.tools.computer_tools.run_command") as command,
        pytest.raises(ConfirmationRequired),
    ):
        _computer_settings_sync("shutdown", None, False)
    command.assert_not_called()


def test_confirmed_shutdown_uses_argument_list() -> None:
    with (
        patch("backend.app.tools.computer_tools.require_platform", return_value="Windows"),
        patch("backend.app.tools.computer_tools.run_command") as command,
    ):
        result = _computer_settings_sync("shutdown", None, True)
    assert result["completed"] is True
    command.assert_called_once_with(["shutdown.exe", "/s", "/t", "0"])


def test_computer_control_validates_coordinates_and_keys() -> None:
    gui = MagicMock()
    gui.size.return_value = (1920, 1080)
    with patch("backend.app.tools.computer_tools._pyautogui", return_value=gui):
        result = _computer_control_sync("click", "", 100, 200, "left", "", None, 0, 0.2, "")
        assert result["completed"] is True
        gui.click.assert_called_once_with(100, 200, clicks=1, interval=0.2, button="left")
        with pytest.raises(ValueError, match="Unsupported keyboard key"):
            _computer_control_sync("press", "", None, None, "left", "launch_shell", None, 0, 0.2, "")
        with pytest.raises(ValueError, match="x must be between"):
            _computer_control_sync("click", "", 5000, 20, "left", "", None, 0, 0.2, "")


def test_typing_returns_count_not_sensitive_text() -> None:
    gui = MagicMock()
    gui.size.return_value = (1920, 1080)
    with patch("backend.app.tools.computer_tools._pyautogui", return_value=gui):
        result = _computer_control_sync("type", "private value", None, None, "left", "", None, 0, 0.01, "")
    assert result == {"action": "type", "completed": True, "characters_typed": 13}
    assert "private value" not in str(result)

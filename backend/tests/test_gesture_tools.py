from unittest.mock import patch

import pytest

from backend.app.tools.gesture_tools import gesture_control, register_gesture_tools
from backend.app.tools.registry import ToolRegistry
from backend.app.tools.safety import ConfirmationRequired


def test_gesture_tool_registers() -> None:
    registry = ToolRegistry()
    register_gesture_tools(registry)
    assert registry.names == ("gesture_control",)
    assert registry.declarations()


@pytest.mark.asyncio
async def test_gesture_start_requires_confirmation() -> None:
    with patch("backend.app.tools.gesture_tools.require_platform", return_value="Windows"):
        with pytest.raises(ConfirmationRequired):
            await gesture_control("start", confirmed=False)


@pytest.mark.asyncio
async def test_gesture_status_and_stop_do_not_open_camera() -> None:
    with patch("backend.app.tools.gesture_tools.require_platform", return_value="Windows"):
        status = await gesture_control("status")
        stopped = await gesture_control("stop")
    assert status["running"] is False
    assert stopped["stopped"] is True

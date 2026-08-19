from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.tools.integration_tools import (
    _private_host,
    _youtube_video_id,
    register_integration_tools,
    send_message,
    smart_home_control,
)
from backend.app.tools.registry import ToolRegistry
from backend.app.tools.safety import ConfirmationRequired


def test_integration_tools_register() -> None:
    registry = ToolRegistry()
    register_integration_tools(registry)
    assert registry.names == ("send_message", "youtube_video", "screen_process", "smart_home_control")


@pytest.mark.asyncio
async def test_message_opens_composer_but_does_not_claim_sent() -> None:
    with patch("backend.app.tools.integration_tools._open_external") as opened:
        with pytest.raises(ConfirmationRequired):
            await send_message("whatsapp", "+1 555 010 1234", "Hello", False)
        result = await send_message("whatsapp", "+1 555 010 1234", "Hello", True)
    assert result["composer_opened"] is True
    assert result["sent"] is False
    assert opened.call_args.args[0].startswith("https://wa.me/15550101234?")


def test_youtube_ids_are_strict() -> None:
    assert _youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _youtube_video_id("https://example.com/watch?v=dQw4w9WgXcQ") is None


def test_smart_home_hosts_must_be_private_literal_ips() -> None:
    assert _private_host("192.168.1.25") == "192.168.1.25"
    with pytest.raises(ValueError):
        _private_host("example.com")
    with pytest.raises(ValueError):
        _private_host("8.8.8.8")
    with pytest.raises(ValueError):
        _private_host("127.0.0.1")


@pytest.mark.asyncio
async def test_smart_home_state_change_requires_confirmation() -> None:
    device = MagicMock()
    device.alias = "Desk light"
    device.model = "Test"
    device.is_on = False
    device.update = AsyncMock()
    device.turn_on = AsyncMock()
    kasa = MagicMock()
    kasa.Discover.discover_single = AsyncMock(return_value=device)
    with patch("backend.app.tools.integration_tools.require_optional_dependency", return_value=kasa):
        with pytest.raises(ConfirmationRequired):
            await smart_home_control("turn_on", "192.168.1.25", False)
        result = await smart_home_control("turn_on", "192.168.1.25", True)
    assert result["action"] == "turn_on"
    device.turn_on.assert_awaited_once()

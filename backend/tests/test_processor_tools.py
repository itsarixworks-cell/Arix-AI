from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.tools.processor_tools import (
    _file_processor_sync,
    _installed_steam_games,
    flight_finder,
    register_processor_tools,
)
from backend.app.tools.registry import ToolRegistry


def test_processor_tools_register() -> None:
    registry = ToolRegistry()
    register_processor_tools(registry)
    assert registry.names == ("game_updater", "flight_finder", "file_processor")


def test_steam_manifest_is_parsed(tmp_path: Path) -> None:
    steamapps = tmp_path / "steamapps"
    steamapps.mkdir()
    (steamapps / "appmanifest_10.acf").write_text(
        '"AppState"\n{\n"appid" "10"\n"name" "Example Game"\n"StateFlags" "4"\n}',
        encoding="utf-8",
    )
    games = _installed_steam_games(tmp_path)
    assert games[0]["appid"] == "10"
    assert games[0]["name"] == "Example Game"


@pytest.mark.asyncio
async def test_flight_search_validation_and_url() -> None:
    departure = (date.today() + timedelta(days=10)).isoformat()
    result = await flight_finder("jfk", "lhr", departure, adults=2, open_browser=False)
    assert result["origin"] == "JFK"
    assert result["destination"] == "LHR"
    assert result["opened"] is False
    assert result["url"].startswith("https://www.google.com/travel/flights?")
    with pytest.raises(ValueError, match="three-letter"):
        await flight_finder("New York", "LHR", departure, open_browser=False)


def test_text_and_json_processing(tmp_path: Path) -> None:
    text = tmp_path / "notes.txt"
    text.write_text("Arix tools are safe. Arix tools are tested.", encoding="utf-8")
    data = tmp_path / "data.json"
    data.write_text('{"b":2,"a":1}', encoding="utf-8")

    def safe_path(raw: str, must_exist: bool = False):
        path = Path(raw)
        if must_exist and not path.exists():
            raise FileNotFoundError(raw)
        return path

    with patch("backend.app.tools.processor_tools.resolve_user_path", side_effect=safe_path):
        count = _file_processor_sync("word_count", str(text), "", None, None, 85, "", "", False, False, False)
        formatted = _file_processor_sync("format", str(data), "", None, None, 85, "", "", False, False, False)
    assert count["words"] == 8
    output = Path(formatted["output_path"])
    assert output.exists()
    assert '  "a": 1' in output.read_text(encoding="utf-8")

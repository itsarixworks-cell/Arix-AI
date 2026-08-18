from pathlib import Path

import pytest

from backend.app.memory.runtime import create_memory_runtime
from backend.app.tools import system_tools


@pytest.mark.asyncio
async def test_safe_system_tools_are_registered(tmp_path: Path) -> None:
    runtime = await create_memory_runtime(tmp_path)
    assert {"open_app", "web_search", "weather_report"}.issubset(runtime.tools.names)


@pytest.mark.asyncio
async def test_open_app_accepts_https_and_rejects_unsafe_schemes(monkeypatch) -> None:
    opened: list[str] = []

    def fake_open(url: str, _new: int) -> bool:
        opened.append(url)
        return True

    monkeypatch.setattr(system_tools.webbrowser, "open", fake_open)
    result = await system_tools.open_app("example.com")
    assert result == {"opened": True, "kind": "website", "target": "https://example.com"}
    assert opened == ["https://example.com"]

    with pytest.raises(ValueError, match="HTTP or HTTPS"):
        await system_tools.open_app("file:///etc/passwd", "website")


@pytest.mark.asyncio
async def test_web_search_returns_bounded_structured_results(monkeypatch) -> None:
    document = """
    <html><body>
      <a class="result__a" href="https://example.com/one">First result</a>
      <a class="result__snippet">Useful first snippet.</a>
      <a class="result__a" href="https://example.com/two">Second result</a>
      <a class="result__snippet">Useful second snippet.</a>
    </body></html>
    """
    monkeypatch.setattr(system_tools, "_request_text", lambda _url: document)

    result = await system_tools.web_search(query="safe automation", max_results=1)
    assert result["query"] == "safe automation"
    assert result["result_count"] == 1
    assert result["results"][0] == {
        "title": "First result",
        "url": "https://example.com/one",
        "snippet": "Useful first snippet.",
    }


@pytest.mark.asyncio
async def test_weather_report_normalizes_provider_payload(monkeypatch) -> None:
    payload = {
        "current_condition": [{
            "temp_C": "18",
            "FeelsLikeC": "17",
            "humidity": "61",
            "windspeedKmph": "12",
            "winddir16Point": "NW",
            "precipMM": "0.0",
            "visibility": "10",
            "weatherDesc": [{"value": "Partly cloudy"}],
        }],
        "nearest_area": [{
            "areaName": [{"value": "London"}],
            "country": [{"value": "United Kingdom"}],
        }],
    }
    monkeypatch.setattr(system_tools, "_request_json", lambda _url: payload)

    result = await system_tools.weather_report(" London ")
    assert result["city"] == "London"
    assert result["condition"] == "Partly cloudy"
    assert result["temperature_c"] == "18"
    assert result["provider"] == "wttr.in"

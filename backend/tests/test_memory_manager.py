from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.memory.manager import GeminiMemoryManager
from backend.app.memory.repository import LocalGraphRepository


class FakeModels:
    async def generate_content(self, **_kwargs):
        return SimpleNamespace(function_calls=[SimpleNamespace(
            name="write_memory_graph",
            args={"nodes": [{
                "title": "Preferred IDE",
                "summary": "The user prefers Visual Studio Code.",
                "category": "preferences",
                "importance": 0.65,
                "related_titles": [],
            }]},
        )])


class FakeAsyncClient:
    def __init__(self) -> None:
        self.models = FakeModels()

    async def aclose(self) -> None:
        return


class FakeClient:
    def __init__(self) -> None:
        self.aio = FakeAsyncClient()


@pytest.mark.asyncio
async def test_manager_ingestion_uses_tool_call_to_write_graph(tmp_path: Path) -> None:
    repository = LocalGraphRepository(tmp_path / "graph.json")
    await repository.ensure_anchors()
    manager = GeminiMemoryManager("placeholder", repository)
    await manager.client.aio.aclose()
    manager.client = FakeClient()

    await manager.ingest("User: I prefer Visual Studio Code.")
    snapshot = await repository.snapshot()
    memory = next(node for node in snapshot.nodes.values() if node.title == "Preferred IDE")
    assert memory.summary == "The user prefers Visual Studio Code."
    assert "user_root" in snapshot.edges[memory.id]

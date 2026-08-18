from pathlib import Path

import pytest

from backend.app.memory.models import CATEGORY_COLORS, MemoryNode
from backend.app.memory.repository import LocalGraphRepository
from backend.app.memory.scratchpad import TierOneScratchpad
from backend.app.memory.service import MemoryService


@pytest.mark.asyncio
async def test_tier_one_save_and_layered_retrieval(tmp_path: Path) -> None:
    repository = LocalGraphRepository(tmp_path / "graph.json")
    await repository.ensure_anchors()
    project = MemoryNode(
        id="arix-project", title="Arix Project", summary="A voice-first desktop assistant.",
        category="projects", color=CATEGORY_COLORS["projects"], source="manager",
    )
    language = MemoryNode(
        id="python", title="Python", summary="The backend targets Python 3.11.",
        category="preferences", color=CATEGORY_COLORS["preferences"], source="manager",
    )
    await repository.upsert_node(project)
    await repository.upsert_node(language)
    await repository.connect("arix-project", "user_root", "owned_by", 0.9)
    await repository.connect("arix-project", "python", "uses", 0.8)
    ingested: list[tuple[str, str]] = []

    async def ingest(text: str, source: str) -> None:
        ingested.append((text, source))

    service = MemoryService(repository, TierOneScratchpad(tmp_path / "tier1.txt"), ingest=ingest)
    await service.save_direct("The user prefers concise answers.")
    assert ingested == [("The user prefers concise answers.", "live_direct")]
    assert "prefers concise answers" in await service.scratchpad.read()

    result = await service.request("Arix Project", depth=1)
    assert result["matched"] is True
    titles = {item["title"] for item in result["memories"]}
    assert {"Arix Project", "Python", "User"}.issubset(titles)


@pytest.mark.asyncio
async def test_uncertain_match_requests_escalation(tmp_path: Path) -> None:
    service = MemoryService(
        LocalGraphRepository(tmp_path / "graph.json"), TierOneScratchpad(tmp_path / "tier1.txt")
    )
    result = await service.request("something conceptual", allow_escalation=False)
    assert result["escalation_required"] is True

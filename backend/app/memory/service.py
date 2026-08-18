from __future__ import annotations

import difflib
import re
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from backend.app.memory.repository import GraphRepository
from backend.app.memory.scratchpad import TierOneScratchpad

IngestCallback = Callable[[str, str], Awaitable[None]]
EscalateCallback = Callable[[str], Awaitable[str]]


class MemoryService:
    def __init__(
        self,
        repository: GraphRepository,
        scratchpad: TierOneScratchpad,
        ingest: IngestCallback | None = None,
        escalate: EscalateCallback | None = None,
    ) -> None:
        self.repository = repository
        self.scratchpad = scratchpad
        self.ingest = ingest
        self.escalate = escalate

    def set_manager(self, ingest: IngestCallback, escalate: EscalateCallback) -> None:
        self.ingest = ingest
        self.escalate = escalate

    async def session_context(self, index_limit: int = 80) -> str:
        scratchpad = await self.scratchpad.read()
        index = await self.repository.title_index(index_limit)
        titles = "\n".join(
            f"- {entry.title} [{entry.category}]" for entry in index.values()
        ) or "- No graph memories yet"
        return (
            "\n\n[TIER-1 PRIVATE MEMORY — use naturally]\n"
            f"{scratchpad or '(empty)'}\n"
            "[LONG-TERM MEMORY TITLE INDEX — titles only; call request_memory for summaries]\n"
            f"{titles}\n"
        )

    async def save_direct(self, text: str) -> dict[str, Any]:
        saved = await self.scratchpad.append(text)
        if self.ingest:
            await self.ingest(text, "live_direct")
        return {"saved": True, "tier": 1, "entry": saved}

    @staticmethod
    def _normalized(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    async def _match(self, query: str) -> tuple[str | None, float]:
        index = await self.repository.title_index(200)
        normalized = self._normalized(query)
        best_id: str | None = None
        best_score = 0.0
        for node_id, entry in index.items():
            title = self._normalized(entry.title)
            if title == normalized:
                return node_id, 1.0
            if normalized in title or title in normalized:
                score = 0.92
            else:
                score = difflib.SequenceMatcher(None, normalized, title).ratio()
            if score > best_score:
                best_id, best_score = node_id, score
        return best_id, best_score

    async def request(self, title: str, depth: int = 1, allow_escalation: bool = True) -> dict[str, Any]:
        depth = max(0, min(4, depth))
        node_id, confidence = await self._match(title)
        if not node_id or confidence < 0.78:
            if allow_escalation and self.escalate:
                return {"matched": False, "escalated": True, "answer": await self.escalate(title)}
            return {"matched": False, "escalation_required": True, "confidence": round(confidence, 3)}

        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])
        memories: list[dict[str, Any]] = []
        while queue:
            current_id, current_depth = queue.popleft()
            if current_id in visited:
                continue
            visited.add(current_id)
            node = await self.repository.get_node(current_id)
            if not node:
                continue
            memories.append({
                "id": node.id, "title": node.title, "summary": node.summary,
                "category": node.category, "distance": current_depth,
            })
            if current_depth < depth:
                for neighbor in await self.repository.get_neighbors(current_id):
                    if neighbor.id not in visited:
                        queue.append((neighbor.id, current_depth + 1))
        return {
            "matched": True,
            "confidence": round(confidence, 3),
            "depth": depth,
            "memories": memories,
        }

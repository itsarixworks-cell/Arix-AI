from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from google import genai
from google.genai import types

from backend.app.memory.models import CATEGORY_COLORS, MemoryNode
from backend.app.memory.repository import GraphRepository

WRITE_TOOL = types.Tool(function_declarations=[types.FunctionDeclaration(
    name="write_memory_graph",
    description="Create or update durable graph memories and their direct relationships.",
    parameters_json_schema={
        "type": "object",
        "properties": {
            "nodes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "summary": {"type": "string"},
                        "category": {"type": "string", "enum": list(CATEGORY_COLORS)},
                        "importance": {"type": "number", "minimum": 0, "maximum": 1},
                        "related_titles": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["title", "summary", "category", "importance", "related_titles"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["nodes"],
        "additionalProperties": False,
    },
)])

ANSWER_TOOL = types.Tool(function_declarations=[types.FunctionDeclaration(
    name="return_memory_answer",
    description="Return a compact synthesized answer from graph memory evidence.",
    parameters_json_schema={
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "matched_titles": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["answer", "matched_titles", "confidence"],
        "additionalProperties": False,
    },
)])


class GeminiMemoryManager:
    """Dedicated Gemini 2.5 Flash process for graph ingestion and fuzzy retrieval."""

    def __init__(self, api_key: str, repository: GraphRepository, model: str = "gemini-2.5-flash") -> None:
        self.repository = repository
        self.model = model
        self.client = genai.Client(api_key=api_key)
        self._ingestions = 0

    @staticmethod
    def _node_id(title: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48] or "memory"
        digest = hashlib.sha1(title.lower().encode(), usedforsecurity=False).hexdigest()[:8]
        return f"{slug}-{digest}"

    async def ingest(self, text: str, source: str = "manager") -> None:
        if not text.strip():
            return
        index = await self.repository.title_index(120)
        known_titles = [entry.title for entry in index.values()]
        prompt = (
            "Review the material and call write_memory_graph exactly once. Extract only durable, useful "
            "facts—not greetings, one-time commands, generated answers, weather, or transient state. "
            "Use concise standalone summaries. Prefer an existing title when it represents the same fact. "
            "related_titles must contain only directly related known/new titles. Returning an empty nodes array "
            "is correct when nothing is durable.\n\n"
            f"Known titles: {json.dumps(known_titles, ensure_ascii=False)}\n"
            f"Material source: {source}\nMaterial:\n{text[:12000]}"
        )
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                tools=[WRITE_TOOL],
                tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(
                    mode="ANY", allowed_function_names=["write_memory_graph"]
                )),
            ),
        )
        for call in response.function_calls or []:
            if call.name == "write_memory_graph":
                await self._write_nodes((call.args or {}).get("nodes", []), source)
        self._ingestions += 1
        if self._ingestions % 20 == 0:
            await self.maintain()

    async def _write_nodes(self, items: list[dict[str, Any]], source: str) -> None:
        index = await self.repository.title_index(300)
        by_title = {entry.title.casefold(): node_id for node_id, entry in index.items()}
        written: dict[str, str] = {}
        for item in items[:12]:
            title = " ".join(str(item.get("title", "")).split())[:120]
            summary = " ".join(str(item.get("summary", "")).split())[:8000]
            category = item.get("category", "notes")
            if not title or not summary or category not in CATEGORY_COLORS:
                continue
            node_id = by_title.get(title.casefold()) or self._node_id(title)
            existing = await self.repository.get_node(node_id)
            importance = max(0.0, min(1.0, float(item.get("importance", 0.5))))
            node = MemoryNode(
                id=node_id,
                title=title,
                summary=summary,
                category=category,
                color=CATEGORY_COLORS[category],
                size=existing.size if existing else 1.0 + importance * 1.5,
                connections=existing.connections if existing else [],
                importance=max(existing.importance, importance) if existing else importance,
                created_at=existing.created_at if existing else datetime.now(UTC).isoformat(),
                last_accessed=datetime.now(UTC).isoformat(),
                access_count=existing.access_count if existing else 0,
                source="live_direct" if source == "live_direct" else "manager",
            )
            await self.repository.upsert_node(node)
            by_title[title.casefold()] = node_id
            written[title.casefold()] = node_id

        for item in items[:12]:
            title_key = str(item.get("title", "")).strip().casefold()
            source_id = written.get(title_key)
            if not source_id:
                continue
            anchor = "ai_root" if title_key.startswith(("arix", "ai ")) else "user_root"
            await self.repository.connect(source_id, anchor, "belongs_to", 0.75)
            for related in item.get("related_titles", [])[:8]:
                target_id = by_title.get(str(related).strip().casefold())
                if target_id and target_id != source_id:
                    await self.repository.connect(source_id, target_id, "related_to", 0.65)

    async def resolve(self, query: str) -> str:
        snapshot = await self.repository.snapshot()
        evidence = [
            {"title": node.title, "summary": node.summary, "category": node.category}
            for node in snapshot.nodes.values()
            if not node.archived and node.id not in {"ai_root", "user_root"}
        ]
        evidence.sort(key=lambda item: len(item["summary"]))
        prompt = (
            "Use only the supplied graph memories. Resolve conceptual/fuzzy relationships and call "
            "return_memory_answer once. Keep the answer compact. Say that memory has no answer if evidence "
            "is insufficient; never invent facts.\n\n"
            f"Question: {query[:2000]}\nGraph memories: {json.dumps(evidence[:180], ensure_ascii=False)}"
        )
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                tools=[ANSWER_TOOL],
                tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(
                    mode="ANY", allowed_function_names=["return_memory_answer"]
                )),
            ),
        )
        for call in response.function_calls or []:
            if call.name == "return_memory_answer":
                arguments = call.args or {}
                return str(arguments.get("answer", "No matching memory was found."))[:4000]
        return "No matching memory was found."

    async def maintain(self, max_age_days: int = 180, importance_floor: float = 0.2) -> dict[str, int]:
        """Conservative decay: merge stale low-value nodes into a related node, otherwise archive."""
        snapshot = await self.repository.snapshot()
        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
        merged = archived = 0
        for node in snapshot.nodes.values():
            if node.id in {"ai_root", "user_root"} or node.archived or node.importance > importance_floor:
                continue
            try:
                last_accessed = datetime.fromisoformat(node.last_accessed)
            except ValueError:
                continue
            if last_accessed > cutoff or node.access_count > 1:
                continue
            neighbors = [
                snapshot.nodes.get(edge.to) for edge in node.connections
                if edge.to not in {"ai_root", "user_root"}
            ]
            target = next((item for item in neighbors if item and not item.archived and item.category == node.category), None)
            if target:
                target.summary = f"{target.summary} Related archived note: {node.summary}"[:8000]
                target.importance = min(1.0, target.importance + node.importance * 0.1)
                await self.repository.upsert_node(target)
                merged += 1
            await self.repository.archive_node(node.id)
            archived += 1
        return {"merged": merged, "archived": archived}

    async def close(self) -> None:
        await self.client.aio.aclose()

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import firebase_admin
from firebase_admin import credentials, db

from backend.app.memory.models import (
    GraphSnapshot,
    MemoryConnection,
    MemoryNode,
    TitleIndexEntry,
    anchor_nodes,
    utc_now,
)
from backend.app.memory.repository import GraphRepository


class FirebaseGraphRepository(GraphRepository):
    """Firebase RTDB adjacency-list repository rooted at /memory."""

    def __init__(
        self,
        database_url: str,
        service_account_path: Path | None = None,
        service_account_json: str = "",
    ) -> None:
        if not database_url.startswith("https://"):
            raise ValueError("ARIX_FIREBASE_DATABASE_URL must be an HTTPS RTDB URL")
        if not firebase_admin._apps:
            if service_account_json:
                credential = credentials.Certificate(json.loads(service_account_json))
            elif service_account_path:
                credential = credentials.Certificate(str(service_account_path))
            else:
                credential = credentials.ApplicationDefault()
            firebase_admin.initialize_app(credential, {"databaseURL": database_url})
        self.root = db.reference("memory")

    async def _get(self, path: str = "") -> Any:
        return await asyncio.to_thread(self.root.child(path).get) if path else await asyncio.to_thread(self.root.get)

    async def _set(self, path: str, value: Any) -> None:
        await asyncio.to_thread(self.root.child(path).set, value)

    async def ensure_anchors(self) -> None:
        for node_id, node in anchor_nodes().items():
            existing = await self._get(f"nodes/{node_id}")
            if not existing:
                await self.upsert_node(node)
            await self._set(f"anchors/{node_id}", True)

    async def upsert_node(self, node: MemoryNode) -> None:
        await self._set(f"nodes/{node.id}", node.model_dump(mode="json"))
        index = TitleIndexEntry(
            title=node.title, category=node.category, color=node.color,
            importance=node.importance, last_accessed=node.last_accessed,
        )
        await self._set(f"title_index/{node.id}", index.model_dump(mode="json"))

    async def connect(self, source: str, target: str, relation: str, weight: float) -> None:
        if source == target:
            return
        source_node, target_node = await asyncio.gather(self.get_node(source), self.get_node(target))
        if not source_node or not target_node:
            raise KeyError("Both memory nodes must exist before connecting them")
        weight = max(0.0, min(1.0, weight))
        edge = {"relation": relation, "weight": weight}
        await asyncio.gather(
            self._set(f"edges/{source}/{target}", edge),
            self._set(f"edges/{target}/{source}", edge),
        )
        for node, other in ((source_node, target), (target_node, source)):
            node.connections = [item for item in node.connections if item.to != other]
            node.connections.append(MemoryConnection(to=other, relation=relation, weight=weight))
            node.size = min(12.0, max(node.size, 1.0 + len(node.connections) * 0.18))
        await asyncio.gather(self.upsert_node(source_node), self.upsert_node(target_node))

    async def get_node(self, node_id: str) -> MemoryNode | None:
        raw = await self._get(f"nodes/{node_id}")
        if not raw:
            return None
        node = MemoryNode.model_validate(raw)
        if node.archived:
            return None
        node.access_count += 1
        node.last_accessed = utc_now()
        await self.upsert_node(node)
        return node

    async def get_neighbors(self, node_id: str) -> list[MemoryNode]:
        adjacency = await self._get(f"edges/{node_id}") or {}
        raw_nodes = await asyncio.gather(*(self._get(f"nodes/{item}") for item in adjacency))
        return [
            node for raw in raw_nodes
            if raw and not (node := MemoryNode.model_validate(raw)).archived
        ]

    async def title_index(self, limit: int = 80) -> dict[str, TitleIndexEntry]:
        raw = await self._get("title_index") or {}
        entries = [(node_id, TitleIndexEntry.model_validate(value)) for node_id, value in raw.items()]
        entries.sort(key=lambda pair: (pair[1].importance, pair[1].last_accessed), reverse=True)
        return dict(entries[:limit])

    async def snapshot(self) -> GraphSnapshot:
        raw = await self._get() or {}
        nodes = {
            node_id: MemoryNode.model_validate(value)
            for node_id, value in (raw.get("nodes") or {}).items()
        }
        return GraphSnapshot(
            nodes=nodes,
            edges=raw.get("edges") or {},
            title_index={
                node_id: TitleIndexEntry.model_validate(value)
                for node_id, value in (raw.get("title_index") or {}).items()
            },
            anchors=raw.get("anchors") or {"ai_root": True, "user_root": True},
        )

    async def archive_node(self, node_id: str) -> None:
        if node_id in {"ai_root", "user_root"}:
            return
        raw = await self._get(f"nodes/{node_id}")
        if raw:
            node = MemoryNode.model_validate(raw)
            node.archived = True
            await self._set(f"nodes/{node_id}", node.model_dump(mode="json"))
            await self._set(f"title_index/{node_id}", None)

    async def upload_snapshot(self, snapshot: GraphSnapshot) -> None:
        """One-time migration upload preserving the required /memory schema."""
        await asyncio.to_thread(self.root.set, snapshot.model_dump(mode="json"))

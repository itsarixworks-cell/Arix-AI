from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from pathlib import Path

from backend.app.memory.models import (
    GraphSnapshot,
    MemoryConnection,
    MemoryNode,
    TitleIndexEntry,
    anchor_nodes,
    utc_now,
)


class GraphRepository(ABC):
    @abstractmethod
    async def ensure_anchors(self) -> None: ...

    @abstractmethod
    async def upsert_node(self, node: MemoryNode) -> None: ...

    @abstractmethod
    async def connect(self, source: str, target: str, relation: str, weight: float) -> None: ...

    @abstractmethod
    async def get_node(self, node_id: str) -> MemoryNode | None: ...

    @abstractmethod
    async def get_neighbors(self, node_id: str) -> list[MemoryNode]: ...

    @abstractmethod
    async def title_index(self, limit: int = 80) -> dict[str, TitleIndexEntry]: ...

    @abstractmethod
    async def snapshot(self) -> GraphSnapshot: ...

    @abstractmethod
    async def archive_node(self, node_id: str) -> None: ...


class LocalGraphRepository(GraphRepository):
    """Atomic local graph store used offline and as a Firebase development fallback."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()
        self._graph = self._load()

    def _load(self) -> GraphSnapshot:
        if self.path.exists():
            return GraphSnapshot.model_validate_json(self.path.read_text(encoding="utf-8"))
        graph = GraphSnapshot(nodes=anchor_nodes())
        for node_id, node in graph.nodes.items():
            graph.title_index[node_id] = TitleIndexEntry(
                title=node.title, category=node.category, color=node.color,
                importance=node.importance, last_accessed=node.last_accessed,
            )
        return graph

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(self._graph.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(self.path)

    async def ensure_anchors(self) -> None:
        async with self._lock:
            for node_id, node in anchor_nodes().items():
                if node_id not in self._graph.nodes:
                    self._graph.nodes[node_id] = node
                    self._graph.title_index[node_id] = TitleIndexEntry(
                        title=node.title, category=node.category, color=node.color,
                        importance=node.importance, last_accessed=node.last_accessed,
                    )
            self._persist()

    async def upsert_node(self, node: MemoryNode) -> None:
        async with self._lock:
            self._graph.nodes[node.id] = node
            self._graph.title_index[node.id] = TitleIndexEntry(
                title=node.title, category=node.category, color=node.color,
                importance=node.importance, last_accessed=node.last_accessed,
            )
            self._persist()

    async def connect(self, source: str, target: str, relation: str, weight: float) -> None:
        if source == target:
            return
        async with self._lock:
            if source not in self._graph.nodes or target not in self._graph.nodes:
                raise KeyError("Both memory nodes must exist before connecting them")
            weight = max(0.0, min(1.0, weight))
            self._graph.edges.setdefault(source, {})[target] = {"relation": relation, "weight": weight}
            self._graph.edges.setdefault(target, {})[source] = {"relation": relation, "weight": weight}
            for current, other in ((source, target), (target, source)):
                node = self._graph.nodes[current]
                node.connections = [edge for edge in node.connections if edge.to != other]
                node.connections.append(MemoryConnection(to=other, relation=relation, weight=weight))
                node.size = min(12.0, max(node.size, 1.0 + len(node.connections) * 0.18))
            self._persist()

    async def get_node(self, node_id: str) -> MemoryNode | None:
        async with self._lock:
            node = self._graph.nodes.get(node_id)
            if not node or node.archived:
                return None
            node.access_count += 1
            node.last_accessed = utc_now()
            self._graph.title_index[node_id].last_accessed = node.last_accessed
            self._persist()
            return node.model_copy(deep=True)

    async def get_neighbors(self, node_id: str) -> list[MemoryNode]:
        async with self._lock:
            neighbor_ids = self._graph.edges.get(node_id, {})
            return [
                self._graph.nodes[item].model_copy(deep=True)
                for item in neighbor_ids
                if item in self._graph.nodes and not self._graph.nodes[item].archived
            ]

    async def title_index(self, limit: int = 80) -> dict[str, TitleIndexEntry]:
        async with self._lock:
            entries = [
                (node_id, entry) for node_id, entry in self._graph.title_index.items()
                if node_id in self._graph.nodes and not self._graph.nodes[node_id].archived
            ]
            entries.sort(key=lambda pair: (pair[1].importance, pair[1].last_accessed), reverse=True)
            return {node_id: entry.model_copy() for node_id, entry in entries[:limit]}

    async def snapshot(self) -> GraphSnapshot:
        async with self._lock:
            return self._graph.model_copy(deep=True)

    async def archive_node(self, node_id: str) -> None:
        if node_id in {"ai_root", "user_root"}:
            return
        async with self._lock:
            if node_id in self._graph.nodes:
                self._graph.nodes[node_id].archived = True
                self._graph.title_index.pop(node_id, None)
                self._persist()

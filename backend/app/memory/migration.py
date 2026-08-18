from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from backend.app.memory.models import (
    CATEGORY_COLORS,
    GraphSnapshot,
    MemoryConnection,
    MemoryNode,
    TitleIndexEntry,
    anchor_nodes,
    utc_now,
)

CATEGORIES = tuple(CATEGORY_COLORS)


def _title(key: str) -> str:
    return re.sub(r"\s+", " ", key.replace("_", " ").replace("-", " ")).strip().title()[:120]


def _node_id(category: str, key: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-")[:48] or "memory"
    digest = hashlib.sha1(f"{category}:{key}".encode(), usedforsecurity=False).hexdigest()[:8]
    return f"{slug}-{digest}"


def _entry_value(entry: Any) -> tuple[str, str | None]:
    if isinstance(entry, dict):
        value = entry.get("value", entry.get("summary", ""))
        return str(value).strip(), entry.get("updated") or entry.get("created_at")
    return str(entry).strip(), None


def convert_flat_memory(data: dict[str, Any]) -> GraphSnapshot:
    snapshot = GraphSnapshot(nodes=anchor_nodes())
    for anchor_id, node in snapshot.nodes.items():
        snapshot.title_index[anchor_id] = TitleIndexEntry(
            title=node.title, category=node.category, color=node.color,
            importance=node.importance, last_accessed=node.last_accessed,
        )

    for category in CATEGORIES:
        entries = data.get(category, {})
        if not isinstance(entries, dict):
            continue
        for key, raw_entry in entries.items():
            summary, old_date = _entry_value(raw_entry)
            if not summary:
                continue
            node_id = _node_id(category, str(key))
            anchor_id = "ai_root" if str(key).lower().startswith(("ai_", "arix_", "brahma_")) else "user_root"
            timestamp = f"{old_date}T00:00:00+00:00" if old_date and "T" not in old_date else old_date or utc_now()
            node = MemoryNode(
                id=node_id,
                title=_title(str(key)),
                summary=summary,
                category=category,
                color=CATEGORY_COLORS[category],
                size=1.25,
                importance=0.6,
                created_at=timestamp,
                last_accessed=timestamp,
                source="migration",
                connections=[MemoryConnection(to=anchor_id, relation="belongs_to", weight=0.8)],
            )
            snapshot.nodes[node_id] = node
            snapshot.nodes[anchor_id].connections.append(
                MemoryConnection(to=node_id, relation="contains", weight=0.8)
            )
            snapshot.edges.setdefault(node_id, {})[anchor_id] = {"relation": "belongs_to", "weight": 0.8}
            snapshot.edges.setdefault(anchor_id, {})[node_id] = {"relation": "contains", "weight": 0.8}
            snapshot.title_index[node_id] = TitleIndexEntry(
                title=node.title, category=node.category, color=node.color,
                importance=node.importance, last_accessed=node.last_accessed,
            )

    for anchor_id in ("ai_root", "user_root"):
        snapshot.nodes[anchor_id].size = min(12.0, 8.0 + len(snapshot.nodes[anchor_id].connections) * 0.08)
    return snapshot


def migrate_file(source: Path, destination: Path) -> GraphSnapshot:
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Legacy memory must be a JSON object")
    snapshot = convert_flat_memory(data)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
    marker = source.with_suffix(source.suffix + ".migrated")
    marker.write_text(
        f"Migrated to graph staging file: {destination}\nThe legacy file is deprecated and was not modified.\n",
        encoding="utf-8",
    )
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert Brahma flat memory to Arix graph memory")
    parser.add_argument("--input", type=Path, default=Path("memory/long_term.json"))
    parser.add_argument("--output", type=Path, default=Path("backend/data/memory_graph.json"))
    args = parser.parse_args()
    snapshot = migrate_file(args.input, args.output)
    print(f"Migrated {len(snapshot.nodes) - 2} memories; anchors preserved: ai_root, user_root")


if __name__ == "__main__":
    main()

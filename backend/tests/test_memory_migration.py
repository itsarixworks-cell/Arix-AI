import json
from pathlib import Path

from backend.app.memory.migration import convert_flat_memory, migrate_file


def test_flat_memory_becomes_anchored_graph() -> None:
    graph = convert_flat_memory({
        "identity": {"name": {"value": "Alex", "updated": "2026-01-02"}},
        "preferences": {"favorite_color": {"value": "Blue"}},
        "projects": {}, "relationships": {}, "wishes": {}, "notes": {},
    })
    assert graph.anchors == {"ai_root": True, "user_root": True}
    assert len(graph.nodes) == 4
    name = next(node for node in graph.nodes.values() if node.title == "Name")
    assert name.summary == "Alex"
    assert name.connections[0].to == "user_root"
    assert graph.edges[name.id]["user_root"]["weight"] == 0.8
    assert name.id in graph.title_index


def test_migration_writes_staging_and_marker(tmp_path: Path) -> None:
    source = tmp_path / "long_term.json"
    output = tmp_path / "memory_graph.json"
    source.write_text(json.dumps({"notes": {"timezone": "UTC"}}), encoding="utf-8")
    graph = migrate_file(source, output)
    assert output.exists()
    assert source.with_suffix(".json.migrated").exists()
    assert any(node.summary == "UTC" for node in graph.nodes.values())

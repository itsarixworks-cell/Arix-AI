from backend.app.memory.migration import convert_flat_memory


def test_graph_snapshot_matches_firebase_paths() -> None:
    snapshot = convert_flat_memory({"notes": {"timezone": {"value": "UTC"}}})
    payload = snapshot.model_dump(mode="json")
    assert set(payload) == {"nodes", "edges", "title_index", "anchors"}
    node_id = next(item for item in payload["nodes"] if item not in {"ai_root", "user_root"})
    assert payload["edges"][node_id]["user_root"]["relation"] == "belongs_to"
    assert payload["edges"]["user_root"][node_id]["relation"] == "contains"
    assert {"title", "category", "color"}.issubset(payload["title_index"][node_id])

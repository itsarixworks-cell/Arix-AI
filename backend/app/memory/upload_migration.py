from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from backend.app.memory.firebase_repository import FirebaseGraphRepository
from backend.app.memory.models import GraphSnapshot


async def upload(source: Path, database_url: str, credential: Path) -> None:
    snapshot = GraphSnapshot.model_validate_json(source.read_text(encoding="utf-8"))
    repository = FirebaseGraphRepository(database_url, service_account_path=credential)
    await repository.upload_snapshot(snapshot)
    await repository.ensure_anchors()
    print(f"Uploaded {len(snapshot.nodes)} nodes to {database_url}/memory")


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload a staged Arix graph migration to Firebase RTDB")
    parser.add_argument("--input", type=Path, default=Path("backend/data/memory_graph.json"))
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--credential", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(upload(args.input, args.database_url, args.credential))


if __name__ == "__main__":
    main()

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path


class TierOneScratchpad:
    """Plain-text, live-model-exclusive memory injected fully into every session."""

    def __init__(self, path: Path, max_chars: int = 16_000) -> None:
        self.path = path
        self.max_chars = max_chars
        self._lock = asyncio.Lock()

    async def read(self) -> str:
        async with self._lock:
            if not self.path.exists():
                return ""
            return self.path.read_text(encoding="utf-8")[-self.max_chars :]

    async def append(self, text: str) -> str:
        clean = " ".join(text.split()).strip()
        if not clean:
            raise ValueError("Memory text cannot be empty")
        timestamp = datetime.now(UTC).isoformat(timespec="seconds")
        line = f"[{timestamp}] {clean}\n"
        async with self._lock:
            existing = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
            merged = (existing + line)[-self.max_chars :]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(merged, encoding="utf-8")
            temporary.replace(self.path)
        return line.strip()

    async def flush(self) -> None:
        # Writes are atomic and immediate; this lock barrier guarantees any active append completed.
        async with self._lock:
            return

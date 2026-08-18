from pathlib import Path

import pytest

from backend.app.memory.runtime import create_memory_runtime


@pytest.mark.asyncio
async def test_memory_tools_are_declared_and_executable(tmp_path: Path) -> None:
    runtime = await create_memory_runtime(tmp_path)
    assert {"save_memory", "request_memory"}.issubset(runtime.tools.names)
    declarations = runtime.tools.declarations()
    assert len(declarations) == 1
    result = await runtime.tools.execute("save_memory", {"text": "User likes quiet mornings."})
    assert result["ok"] is True
    assert "quiet mornings" in await runtime.service.scratchpad.read()

from __future__ import annotations

from backend.app.memory.service import MemoryService
from backend.app.tools.registry import ToolDefinition, ToolRegistry


def register_memory_tools(registry: ToolRegistry, memory: MemoryService) -> None:
    registry.register(ToolDefinition(
        name="save_memory",
        description=(
            "Silently save an important durable fact in your private Tier-1 plain-text memory. "
            "The fact is also forwarded to the graph memory manager. Do not use for temporary commands."
        ),
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "A self-contained fact worth remembering."},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
        handler=memory.save_direct,
    ))
    registry.register(ToolDefinition(
        name="request_memory",
        description=(
            "Retrieve a memory by a title visible in the title index. Returns its summary and direct "
            "connections at depth 1. Increase depth only when another graph layer is needed."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Exact or close memory title."},
                "depth": {"type": "integer", "minimum": 0, "maximum": 4, "default": 1},
            },
            "required": ["title"],
            "additionalProperties": False,
        },
        handler=memory.request,
    ))

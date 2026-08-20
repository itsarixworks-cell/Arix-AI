from __future__ import annotations

import inspect
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.genai import types

ToolHandler = Callable[..., dict[str, Any] | Awaitable[dict[str, Any]]]
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler


class ToolRegistry:
    def __init__(self, audit_path: Path | None = None) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._audit_path = audit_path

    def _audit(self, name: str, arguments: dict[str, Any], result: dict[str, Any], duration_ms: int) -> None:
        if not self._audit_path:
            return
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": name,
            "argument_keys": sorted(arguments),
            "ok": bool(result.get("ok")),
            "error_code": result.get("error_code"),
            "duration_ms": duration_ms,
        }
        try:
            self._audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self._audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            logger.warning("Could not append the local tool audit record")

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"Tool already registered: {definition.name}")
        self._tools[definition.name] = definition

    def declarations(self) -> list[types.Tool]:
        declarations = [
            types.FunctionDeclaration(
                name=item.name,
                description=item.description,
                parameters_json_schema=item.parameters,
            )
            for item in self._tools.values()
        ]
        return [types.Tool(function_declarations=declarations)] if declarations else []

    async def execute(self, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        started = time.monotonic()
        supplied = dict(arguments or {})
        definition = self._tools.get(name)
        if not definition:
            result = {
                "ok": False,
                "error": f"Unknown tool: {name}",
                "error_code": "unknown_tool",
                "tool": name,
                "duration_ms": 0,
            }
            self._audit(name, supplied, result, 0)
            return result
        try:
            output = definition.handler(**supplied)
            if inspect.isawaitable(output):
                output = await output
            if not isinstance(output, dict):
                raise TypeError(f"Tool {name} returned a non-object result")
            result = {"ok": True, "result": output}
        except Exception as error:
            error_name = type(error).__name__
            if error_name == "ConfirmationRequired":
                code = "confirmation_required"
            elif isinstance(error, (FileNotFoundError, PermissionError)):
                code = "path_error"
            elif isinstance(error, (ValueError, TypeError)):
                code = "invalid_arguments"
            elif isinstance(error, RuntimeError):
                code = "unavailable"
            else:
                code = "execution_failed"
            result = {
                "ok": False,
                "error": str(error)[:500] or error_name,
                "error_code": code,
                "tool": name,
            }
        duration_ms = round((time.monotonic() - started) * 1000)
        result["duration_ms"] = duration_ms
        self._audit(name, supplied, result, duration_ms)
        return result

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

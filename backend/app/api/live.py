from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from backend.app.core.config import settings
from backend.app.core.protocol import SessionStart, TextInput
from backend.app.services.gemini_live import GeminiLiveBridge

logger = logging.getLogger(__name__)
router = APIRouter()


async def _send_events(websocket: WebSocket, queue: asyncio.Queue[dict]) -> None:
    while True:
        event = await queue.get()
        try:
            await websocket.send_json(event)
        finally:
            queue.task_done()


@router.websocket("/ws/live")
async def live_socket(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin")
    if origin and origin not in settings.allowed_origins and not origin.startswith("file://"):
        await websocket.close(code=1008, reason="Origin is not allowed")
        return

    await websocket.accept()
    events: asyncio.Queue[dict] = asyncio.Queue()
    sender = asyncio.create_task(_send_events(websocket, events))
    bridge: GeminiLiveBridge | None = None
    bridge_task: asyncio.Task | None = None

    async def emit(event: dict) -> None:
        await events.put(event)

    try:
        first = await websocket.receive_text()
        try:
            start = SessionStart.model_validate_json(first)
        except ValidationError:
            await emit({"type": "error", "code": "invalid_session", "message": "Invalid session configuration"})
            return

        api_key = start.api_key.strip() or settings.fallback_api_key
        if not api_key:
            await emit({"type": "error", "code": "missing_api_key", "message": "A Gemini API key is required"})
            return

        bridge = GeminiLiveBridge(start, api_key, emit)
        bridge_task = asyncio.create_task(bridge.run())

        while True:
            receive_task = asyncio.create_task(websocket.receive())
            done, _ = await asyncio.wait(
                {receive_task, bridge_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if bridge_task in done:
                receive_task.cancel()
                error = bridge_task.exception()
                if error:
                    logger.info("Gemini Live session ended: %s", type(error).__name__)
                    await emit({
                        "type": "error",
                        "code": "gemini_connection",
                        "message": "Gemini Live ended the session. Check the API key, model access, and network connection.",
                    })
                break

            message = receive_task.result()
            if message["type"] == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                await bridge.send_audio(message["bytes"])
            elif message.get("text"):
                try:
                    payload = json.loads(message["text"])
                    if payload.get("type") == "text":
                        text_input = TextInput.model_validate(payload)
                        await bridge.send_text(text_input.text)
                except (json.JSONDecodeError, ValidationError):
                    await emit({"type": "error", "code": "invalid_message", "message": "The message was not valid"})
    except WebSocketDisconnect:
        pass
    except Exception as error:  # The key and message payload are deliberately never logged.
        logger.warning("Live socket failed (%s)", type(error).__name__)
        with contextlib.suppress(Exception):
            await emit({"type": "error", "code": "local_bridge", "message": "The local live bridge encountered an error"})
    finally:
        if bridge:
            await bridge.stop()
        if bridge_task and not bridge_task.done():
            bridge_task.cancel()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(events.join(), timeout=0.25)
        sender.cancel()

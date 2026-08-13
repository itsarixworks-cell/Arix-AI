from __future__ import annotations

import asyncio
import base64
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

from google import genai
from google.genai import types

from backend.app.core.protocol import SessionStart

EventSink = Callable[[dict[str, Any]], Awaitable[None]]


class GeminiLiveBridge:
    """Owns one Gemini Live session and translates it to Arix protocol events."""

    def __init__(self, config: SessionStart, api_key: str, emit: EventSink) -> None:
        self.config = config
        self.api_key = api_key
        self.emit = emit
        self._client = genai.Client(api_key=api_key)
        self._session: Any | None = None
        self._send_queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue(maxsize=128)
        self._stopping = asyncio.Event()

    def _live_config(self) -> types.LiveConnectConfig:
        return types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.config.voice)
                )
            ),
            system_instruction=self.config.system_instruction,
        )

    async def run(self) -> None:
        await self.emit({"type": "status", "status": "connecting", "message": "Connecting to Gemini Live"})
        async with self._client.aio.live.connect(
            model=self.config.model,
            config=self._live_config(),
        ) as session:
            self._session = session
            await self.emit({"type": "session.ready", "model": self.config.model})
            send_task = asyncio.create_task(self._send_loop())
            receive_task = asyncio.create_task(self._receive_loop())
            stop_task = asyncio.create_task(self._stopping.wait())
            done, pending = await asyncio.wait(
                {send_task, receive_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                if task is not stop_task:
                    task.result()
        self._session = None

    async def _send_loop(self) -> None:
        while not self._stopping.is_set():
            kind, payload = await self._send_queue.get()
            if self._session is None:
                continue
            if kind == "audio":
                await self._session.send_realtime_input(
                    audio=types.Blob(data=payload, mime_type="audio/pcm;rate=16000")
                )
            elif kind == "text":
                await self._session.send_realtime_input(text=payload)

    async def _receive_loop(self) -> None:
        while not self._stopping.is_set() and self._session is not None:
            async for response in self._session.receive():
                await self._handle_response(response)

    async def _handle_response(self, response: Any) -> None:
        content = getattr(response, "server_content", None)
        if content is None:
            return

        input_transcription = getattr(content, "input_transcription", None)
        if input_transcription and getattr(input_transcription, "text", None):
            await self.emit({
                "type": "transcript",
                "role": "user",
                "text": input_transcription.text,
                "final": False,
            })

        output_transcription = getattr(content, "output_transcription", None)
        if output_transcription and getattr(output_transcription, "text", None):
            await self.emit({
                "type": "transcript",
                "role": "assistant",
                "text": output_transcription.text,
                "final": False,
            })

        model_turn = getattr(content, "model_turn", None)
        for part in getattr(model_turn, "parts", None) or []:
            inline_data = getattr(part, "inline_data", None)
            if inline_data and getattr(inline_data, "data", None):
                data = inline_data.data
                if isinstance(data, str):
                    encoded = data
                else:
                    encoded = base64.b64encode(data).decode("ascii")
                await self.emit({
                    "type": "audio",
                    "data": encoded,
                    "mime_type": getattr(inline_data, "mime_type", None) or "audio/pcm;rate=24000",
                })

        if getattr(content, "interrupted", False):
            await self.emit({"type": "interrupted"})
        if getattr(content, "turn_complete", False):
            await self.emit({"type": "turn.complete"})

    async def send_audio(self, data: bytes) -> None:
        if not data or self._stopping.is_set():
            return
        try:
            self._send_queue.put_nowait(("audio", data))
        except asyncio.QueueFull:
            # Favor fresh real-time audio over delayed audio when the connection is congested.
            with contextlib.suppress(asyncio.QueueEmpty):
                self._send_queue.get_nowait()
            self._send_queue.put_nowait(("audio", data))

    async def send_text(self, text: str) -> None:
        await self._send_queue.put(("text", text))

    async def stop(self) -> None:
        self._stopping.set()


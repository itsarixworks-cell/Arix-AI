from __future__ import annotations

import asyncio
import ipaddress
import json
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

from backend.app.tools.registry import ToolDefinition, ToolRegistry
from backend.app.tools.safety import (
    bounded_number,
    bounded_text,
    require_confirmation,
    require_optional_dependency,
    resolve_user_path,
)

_NETWORK_TIMEOUT = 10
_USER_AGENT = "Arix-AI/0.2 (+local desktop assistant)"


def _open_external(url: str) -> None:
    if not webbrowser.open(url, new=2):
        raise RuntimeError("The default browser did not accept the request")


async def send_message(
    platform: str,
    receiver: str,
    message: str,
    confirmed: bool = False,
) -> dict[str, Any]:
    require_confirmation(f"open a {platform} message addressed to {receiver}", confirmed)
    recipient = bounded_text(receiver, limit=200, field="receiver")
    text = bounded_text(message, limit=4_000, field="message")
    if platform == "whatsapp":
        phone = "".join(character for character in recipient if character.isdigit())
        if not 7 <= len(phone) <= 15:
            raise ValueError("WhatsApp receiver must contain a 7-15 digit international phone number")
        url = f"https://wa.me/{phone}?" + urllib.parse.urlencode({"text": text})
    elif platform == "telegram":
        username = recipient.removeprefix("@").strip()
        if not username.replace("_", "").isalnum():
            raise ValueError("Telegram receiver must be a valid username")
        url = f"https://t.me/{urllib.parse.quote(username)}?" + urllib.parse.urlencode({"text": text})
    elif platform == "email":
        if "@" not in recipient or any(character in recipient for character in "\r\n"):
            raise ValueError("A valid email receiver is required")
        url = "mailto:" + urllib.parse.quote(recipient, safe="@+._-") + "?" + urllib.parse.urlencode({"body": text})
    elif platform == "sms":
        phone = "".join(character for character in recipient if character.isdigit() or character == "+")
        if not 7 <= len(phone.replace("+", "")) <= 15:
            raise ValueError("SMS receiver must contain a valid phone number")
        url = "sms:" + urllib.parse.quote(phone, safe="+") + "?" + urllib.parse.urlencode({"body": text})
    else:
        raise ValueError("platform must be whatsapp, telegram, email, or sms")
    await asyncio.to_thread(_open_external, url)
    return {
        "platform": platform,
        "receiver": recipient,
        "composer_opened": True,
        "sent": False,
        "note": "The message is prepared but the user must review and press Send.",
    }


def _youtube_video_id(value: str) -> str | None:
    parsed = urllib.parse.urlparse(value)
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    if host == "youtu.be":
        candidate = parsed.path.strip("/").split("/")[0]
    elif host in {"youtube.com", "m.youtube.com"}:
        candidate = urllib.parse.parse_qs(parsed.query).get("v", [""])[0]
        if not candidate and parsed.path.startswith("/shorts/"):
            candidate = parsed.path.split("/")[2]
    else:
        return None
    return candidate if len(candidate) == 11 and all(character.isalnum() or character in "-_" for character in candidate) else None


def _request_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=_NETWORK_TIMEOUT) as response:
        return json.loads(response.read(1_000_000))


async def youtube_video(
    action: str,
    query: str = "",
    url: str = "",
    languages: list[str] | None = None,
) -> dict[str, Any]:
    if action in {"play", "search"}:
        if url:
            video_id = _youtube_video_id(url)
            if not video_id:
                raise ValueError("A valid YouTube video URL is required")
            target = f"https://www.youtube.com/watch?v={video_id}"
        else:
            search = bounded_text(query, limit=500, field="query")
            target = "https://www.youtube.com/results?" + urllib.parse.urlencode({"search_query": search})
        await asyncio.to_thread(_open_external, target)
        return {"action": action, "opened": True, "url": target}
    video_id = _youtube_video_id(bounded_text(url, limit=2_000, field="url"))
    if not video_id:
        raise ValueError("A valid YouTube video URL is required")
    canonical = f"https://www.youtube.com/watch?v={video_id}"
    if action == "info":
        data = await asyncio.to_thread(
            _request_json,
            "https://www.youtube.com/oembed?" + urllib.parse.urlencode({"url": canonical, "format": "json"}),
        )
        return {"action": action, "video_id": video_id, "url": canonical, "title": data.get("title", ""), "author": data.get("author_name", ""), "thumbnail_url": data.get("thumbnail_url", "")}
    if action == "transcript":
        transcript_api = require_optional_dependency("youtube_transcript_api", "pip install youtube-transcript-api")
        preferred = [str(item)[:12] for item in (languages or ["en"])][:5]

        def fetch() -> list[dict[str, Any]]:
            api = transcript_api.YouTubeTranscriptApi()
            transcript = api.fetch(video_id, languages=preferred)
            return [{"text": item.text, "start": item.start, "duration": item.duration} for item in transcript][:2_000]

        segments = await asyncio.to_thread(fetch)
        joined = " ".join(segment["text"] for segment in segments)[:100_000]
        return {"action": action, "video_id": video_id, "url": canonical, "text": joined, "segments": segments, "truncated": len(joined) >= 100_000}
    raise ValueError("action must be play, search, info, or transcript")


def _capture_screen(path: str) -> dict[str, Any]:
    target = resolve_user_path(path or str(Path.home() / "Pictures" / "Arix" / "screen_capture.png"))
    if target.suffix.casefold() not in {".png", ".jpg", ".jpeg"}:
        raise ValueError("Screen capture path must end in .png, .jpg, or .jpeg")
    target.parent.mkdir(parents=True, exist_ok=True)
    image_grab = require_optional_dependency("PIL.ImageGrab", "pip install Pillow")
    image = image_grab.grab(all_screens=True)
    image.save(target)
    return {"captured": True, "path": str(target), "width": image.width, "height": image.height}


async def screen_process(action: str, path: str = "") -> dict[str, Any]:
    if action == "capture":
        return {"action": action, **await asyncio.to_thread(_capture_screen, path)}
    target = resolve_user_path(bounded_text(path, limit=2_000, field="path"), must_exist=True)
    image_module = require_optional_dependency("PIL.Image", "pip install Pillow")
    with image_module.open(target) as image:
        if action == "info":
            return {"action": action, "path": str(target), "width": image.width, "height": image.height, "format": image.format, "mode": image.mode}
        if action == "ocr":
            pytesseract = require_optional_dependency("pytesseract", "pip install pytesseract")
            text = await asyncio.to_thread(pytesseract.image_to_string, image.copy())
            return {"action": action, "path": str(target), "text": text[:50_000], "truncated": len(text) > 50_000}
    raise ValueError("action must be capture, info, or ocr")


def _private_host(host: str) -> str:
    try:
        address = ipaddress.ip_address(host.strip())
    except ValueError as error:
        raise ValueError("device_host must be a literal private IP address") from error
    if not address.is_private or address.is_loopback or address.is_unspecified or address.is_multicast:
        raise ValueError("device_host must be a non-loopback private IP address")
    return str(address)


async def smart_home_control(
    action: str,
    device_host: str = "",
    confirmed: bool = False,
    timeout: float = 5,
) -> dict[str, Any]:
    kasa = require_optional_dependency("kasa", "pip install python-kasa")
    bounded_timeout = bounded_number(timeout, minimum=1, maximum=15, field="timeout")
    if action == "discover":
        devices = await kasa.Discover.discover(timeout=bounded_timeout)
        records = []
        for host, device in list(devices.items())[:100]:
            await device.update()
            records.append({"host": str(host), "alias": getattr(device, "alias", ""), "model": getattr(device, "model", ""), "is_on": getattr(device, "is_on", None)})
        return {"action": action, "devices": records, "count": len(records)}
    if action not in {"status", "turn_on", "turn_off", "toggle"}:
        raise ValueError("action must be discover, status, turn_on, turn_off, or toggle")
    host = _private_host(device_host)
    device = await kasa.Discover.discover_single(host, timeout=bounded_timeout)
    if device is None:
        raise RuntimeError("No supported smart-home device responded at that host")
    await device.update()
    if action != "status":
        require_confirmation(f"{action.replace('_', ' ')} smart-home device {host}", confirmed)
        desired = not bool(device.is_on) if action == "toggle" else action == "turn_on"
        await (device.turn_on() if desired else device.turn_off())
        await device.update()
    return {"action": action, "host": host, "alias": getattr(device, "alias", ""), "model": getattr(device, "model", ""), "is_on": bool(device.is_on)}


def register_integration_tools(registry: ToolRegistry) -> None:
    registry.register(ToolDefinition(
        name="send_message",
        description="Open a reviewed message composer for WhatsApp, Telegram, email, or SMS. Always requires confirmation and never claims the message was sent.",
        parameters={"type": "object", "properties": {
            "platform": {"type": "string", "enum": ["whatsapp", "telegram", "email", "sms"]},
            "receiver": {"type": "string"}, "message": {"type": "string", "maxLength": 4000},
            "confirmed": {"type": "boolean", "default": False},
        }, "required": ["platform", "receiver", "message"], "additionalProperties": False},
        handler=send_message,
    ))
    registry.register(ToolDefinition(
        name="youtube_video",
        description="Play or search YouTube, retrieve public video metadata, or fetch a transcript.",
        parameters={"type": "object", "properties": {
            "action": {"type": "string", "enum": ["play", "search", "info", "transcript"]},
            "query": {"type": "string"}, "url": {"type": "string"},
            "languages": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        }, "required": ["action"], "additionalProperties": False},
        handler=youtube_video,
    ))
    registry.register(ToolDefinition(
        name="screen_process",
        description="Capture the screen or inspect/OCR an approved local image. OCR requires optional Tesseract installation.",
        parameters={"type": "object", "properties": {
            "action": {"type": "string", "enum": ["capture", "info", "ocr"]}, "path": {"type": "string"},
        }, "required": ["action"], "additionalProperties": False},
        handler=screen_process,
    ))
    registry.register(ToolDefinition(
        name="smart_home_control",
        description="Discover or control TP-Link Kasa devices on the private local network. State changes require confirmation.",
        parameters={"type": "object", "properties": {
            "action": {"type": "string", "enum": ["discover", "status", "turn_on", "turn_off", "toggle"]},
            "device_host": {"type": "string"}, "confirmed": {"type": "boolean", "default": False},
            "timeout": {"type": "number", "minimum": 1, "maximum": 15, "default": 5},
        }, "required": ["action"], "additionalProperties": False},
        handler=smart_home_control,
    ))

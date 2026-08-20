from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import re
import shutil
import subprocess
import urllib.parse
import webbrowser
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from backend.app.tools.registry import ToolDefinition, ToolRegistry
from backend.app.tools.safety import (
    MAX_TEXT_BYTES,
    atomic_output_path,
    atomic_write_text,
    bounded_number,
    require_confirmation,
    require_optional_dependency,
    require_platform,
    resolve_user_path,
    run_command,
    verify_written_file,
)

_MANIFEST_FIELD = re.compile(r'^\s*"([^"]+)"\s+"([^"]*)"\s*$')
_MAX_CELLS = 100_000


def _steam_root() -> Path | None:
    candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Steam",
        Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Steam",
        Path.home() / ".steam" / "steam",
    ]
    return next((path for path in candidates if (path / "steamapps").exists()), None)


def _steam_libraries(root: Path) -> list[Path]:
    libraries = [root]
    file = root / "steamapps" / "libraryfolders.vdf"
    if file.exists():
        for raw in file.read_text(encoding="utf-8", errors="replace").splitlines():
            match = _MANIFEST_FIELD.match(raw)
            if match and match.group(1).isdigit():
                candidate = Path(match.group(2).replace("\\\\", "\\"))
                if (candidate / "steamapps").exists() and candidate not in libraries:
                    libraries.append(candidate)
    return libraries[:20]


def _installed_steam_games(root: Path) -> list[dict[str, Any]]:
    games = []
    for library in _steam_libraries(root):
        for manifest in (library / "steamapps").glob("appmanifest_*.acf"):
            fields: dict[str, str] = {}
            for raw in manifest.read_text(encoding="utf-8", errors="replace").splitlines():
                match = _MANIFEST_FIELD.match(raw)
                if match:
                    fields[match.group(1)] = match.group(2)
            if fields.get("appid") and fields.get("name"):
                games.append({
                    "appid": fields["appid"], "name": fields["name"],
                    "state_flags": fields.get("StateFlags", ""), "library": str(library),
                })
    return sorted(games, key=lambda item: item["name"].casefold())[:1_000]


def _game_updater_sync(action: str, game_name: str, app_id: str, confirmed: bool) -> dict[str, Any]:
    require_platform("Windows")
    root = _steam_root()
    if not root:
        raise RuntimeError("Steam installation was not found")
    games = _installed_steam_games(root)
    if action == "list":
        return {"action": action, "platform": "steam", "games": games, "count": len(games)}
    if action == "status":
        active = [game for game in games if game["state_flags"] not in {"4", ""}]
        return {"action": action, "platform": "steam", "active": active, "count": len(active)}
    if action not in {"update", "install"}:
        raise ValueError("action must be list, status, update, or install")
    selected_id = "".join(character for character in app_id if character.isdigit())
    matched = None
    if game_name:
        needle = game_name.casefold().strip()
        matched = next((game for game in games if needle == game["name"].casefold()), None)
        matched = matched or next((game for game in games if needle in game["name"].casefold()), None)
        if matched:
            selected_id = matched["appid"]
    if not selected_id:
        raise ValueError("A numeric Steam app_id or installed game_name is required")
    require_confirmation(f"ask Steam to {action} app {selected_id}", confirmed)
    subprocess.Popen(
        [str(root / "steam.exe"), "-silent"], stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False,
    )
    uri = f"steam://install/{selected_id}"
    if not webbrowser.open(uri, new=0):
        raise RuntimeError("Steam did not accept the install/update request")
    return {"action": action, "requested": True, "platform": "steam", "appid": selected_id, "game": matched["name"] if matched else game_name}


async def game_updater(action: str, game_name: str = "", app_id: str = "", confirmed: bool = False) -> dict[str, Any]:
    return await asyncio.to_thread(_game_updater_sync, action, game_name, app_id, confirmed)


def _airport_code(value: str, field: str) -> str:
    code = value.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise ValueError(f"{field} must be a three-letter IATA airport code")
    return code


def _flight_date(value: str, field: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must use YYYY-MM-DD") from error
    if parsed < date.today():
        raise ValueError(f"{field} cannot be in the past")
    return parsed.isoformat()


async def flight_finder(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str = "",
    adults: int = 1,
    travel_class: str = "economy",
    open_browser: bool = True,
) -> dict[str, Any]:
    source = _airport_code(origin, "origin")
    target = _airport_code(destination, "destination")
    if source == target:
        raise ValueError("origin and destination must differ")
    depart = _flight_date(departure_date, "departure_date")
    returning = _flight_date(return_date, "return_date") if return_date else ""
    if returning and returning < depart:
        raise ValueError("return_date cannot be before departure_date")
    passengers = int(bounded_number(adults, minimum=1, maximum=9, field="adults"))
    if travel_class not in {"economy", "premium_economy", "business", "first"}:
        raise ValueError("Unsupported travel_class")
    words = f"Flights from {source} to {target} on {depart}"
    if returning:
        words += f" returning {returning}"
    words += f" for {passengers} adult{'s' if passengers != 1 else ''} {travel_class.replace('_', ' ')}"
    url = "https://www.google.com/travel/flights?" + urllib.parse.urlencode({"q": words})
    if open_browser:
        opened = await asyncio.to_thread(webbrowser.open, url, 2)
        if not opened:
            raise RuntimeError("The default browser did not accept the flight search")
    return {"origin": source, "destination": target, "departure_date": depart, "return_date": returning or None, "adults": passengers, "travel_class": travel_class, "url": url, "opened": open_browser}


def _output_path(source: Path, output_path: str, suffix: str, extension: str | None = None) -> Path:
    if output_path:
        return resolve_user_path(output_path)
    return source.with_name(source.stem + suffix + (extension or source.suffix))


def _write_guard(target: Path, confirmed: bool, overwrite: bool) -> None:
    if target.exists():
        require_confirmation("overwrite the processed output file", confirmed and overwrite)
    target.parent.mkdir(parents=True, exist_ok=True)


def _file_processor_sync(
    action: str, path: str, output_path: str, width: int | None, height: int | None,
    quality: int, column: str, value: str, descending: bool, confirmed: bool, overwrite: bool,
    start_seconds: float = 0, end_seconds: float = 0,
) -> dict[str, Any]:
    source = resolve_user_path(path, must_exist=True)
    if not source.is_file():
        raise ValueError("path must be a file")
    extension = source.suffix.casefold()
    if action == "info":
        stat = source.stat()
        return {"action": action, "path": str(source), "extension": extension, "bytes": stat.st_size, "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()}
    if extension in {".txt", ".md", ".log", ".py", ".js", ".ts", ".json", ".csv"} and source.stat().st_size > MAX_TEXT_BYTES:
        raise ValueError("text/data file exceeds the 1 MB processing limit")
    if extension in {".txt", ".md", ".log", ".py", ".js", ".ts"}:
        text = source.read_text(encoding="utf-8", errors="replace")
        if action == "extract_text":
            return {"action": action, "path": str(source), "text": text, "characters": len(text)}
        if action == "word_count":
            words = re.findall(r"\b[\w'-]+\b", text.casefold())
            return {"action": action, "path": str(source), "words": len(words), "lines": len(text.splitlines()), "characters": len(text), "common_words": Counter(words).most_common(20)}
    if extension == ".json":
        data = json.loads(source.read_text(encoding="utf-8"))
        if action == "validate":
            return {"action": action, "path": str(source), "valid": True, "kind": type(data).__name__}
        if action == "format":
            target = _output_path(source, output_path, "_formatted", ".json")
            _write_guard(target, confirmed, overwrite)
            atomic_write_text(target, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            verified = verify_written_file(target)
            return {"action": action, "completed": True, "output_path": str(target), **verified}
    if extension == ".csv":
        with source.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)[:20_000]
            fields = reader.fieldnames or []
        if action == "stats":
            return {"action": action, "path": str(source), "rows": len(rows), "columns": fields, "column_count": len(fields)}
        if column not in fields:
            raise ValueError("column must match a CSV header")
        if action == "filter":
            selected = [row for row in rows if value.casefold() in str(row.get(column, "")).casefold()]
        elif action == "sort":
            selected = sorted(rows, key=lambda row: str(row.get(column, "")).casefold(), reverse=descending)
        else:
            selected = []
        if action in {"filter", "sort"}:
            target = _output_path(source, output_path, f"_{action}", ".csv")
            _write_guard(target, confirmed, overwrite)
            buffer = io.StringIO(newline="")
            writer = csv.DictWriter(buffer, fieldnames=fields)
            writer.writeheader()
            writer.writerows(selected)
            atomic_write_text(target, buffer.getvalue())
            verified = verify_written_file(target)
            return {
                "action": action,
                "completed": True,
                "output_path": str(target),
                **verified,
                "rows": len(selected),
            }
    if extension in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        image_module = require_optional_dependency("PIL.Image", "pip install Pillow")
        with image_module.open(source) as image:
            if action == "image_info":
                return {"action": action, "path": str(source), "width": image.width, "height": image.height, "format": image.format, "mode": image.mode}
            if action in {"resize", "compress", "convert"}:
                target_extension = Path(output_path).suffix if output_path else (".jpg" if action == "convert" else source.suffix)
                if target_extension.casefold() not in {".png", ".jpg", ".jpeg", ".webp"}:
                    raise ValueError("output image must be PNG, JPEG, or WebP")
                target = _output_path(source, output_path, f"_{action}", target_extension)
                _write_guard(target, confirmed, overwrite)
                output = image.copy()
                if action == "resize":
                    new_width = int(bounded_number(width, minimum=1, maximum=16_384, field="width"))
                    new_height = int(bounded_number(height, minimum=1, maximum=16_384, field="height"))
                    output.thumbnail((new_width, new_height))
                if target.suffix.casefold() in {".jpg", ".jpeg"} and output.mode not in {"RGB", "L"}:
                    output = output.convert("RGB")
                with atomic_output_path(target) as temporary:
                    output.save(
                        temporary,
                        quality=int(bounded_number(quality, minimum=20, maximum=100, field="quality")),
                        optimize=True,
                    )
                verified = verify_written_file(target)
                return {
                    "action": action,
                    "completed": True,
                    "output_path": str(target),
                    **verified,
                    "width": output.width,
                    "height": output.height,
                }
    if extension in {".xlsx", ".xlsm"} and action == "xlsx_stats":
        openpyxl = require_optional_dependency("openpyxl", "pip install openpyxl")
        workbook = openpyxl.load_workbook(source, read_only=True, data_only=True)
        sheet_stats = []
        total_cells = 0
        try:
            for worksheet in workbook.worksheets[:20]:
                numeric: list[float] = []
                non_empty = 0
                for row in worksheet.iter_rows():
                    for cell in row:
                        total_cells += 1
                        if total_cells > _MAX_CELLS:
                            raise ValueError("workbook exceeds the 100,000-cell analysis limit")
                        if cell.value not in (None, ""):
                            non_empty += 1
                        if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool):
                            numeric.append(float(cell.value))
                sheet_stats.append({
                    "name": worksheet.title,
                    "rows": worksheet.max_row,
                    "columns": worksheet.max_column,
                    "non_empty_cells": non_empty,
                    "numeric_cells": len(numeric),
                    "numeric_min": min(numeric) if numeric else None,
                    "numeric_max": max(numeric) if numeric else None,
                    "numeric_average": (sum(numeric) / len(numeric)) if numeric else None,
                })
        finally:
            workbook.close()
        return {"action": action, "path": str(source), "sheets": sheet_stats, "sheet_count": len(sheet_stats)}
    if extension == ".pdf" and action in {"pdf_info", "extract_text", "pdf_to_word"}:
        pypdf = require_optional_dependency("pypdf", "pip install pypdf")
        reader = pypdf.PdfReader(str(source))
        if action == "pdf_info":
            return {"action": action, "path": str(source), "pages": len(reader.pages), "metadata": {str(key): str(value) for key, value in (reader.metadata or {}).items()}}
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages)[:100_000]
        if action == "extract_text":
            return {"action": action, "path": str(source), "text": text, "truncated": len(text) >= 100_000}
        docx = require_optional_dependency("docx", "pip install python-docx")
        target = _output_path(source, output_path, "_converted", ".docx")
        _write_guard(target, confirmed, overwrite)
        document = docx.Document()
        document.core_properties.title = source.stem
        document.core_properties.author = "Arix AI"
        document.add_heading(source.stem, level=0)
        for page_number, page in enumerate(reader.pages, start=1):
            if page_number > 1:
                document.add_page_break()
            document.add_heading(f"Page {page_number}", level=1)
            for paragraph in (page.extract_text() or "").split("\n"):
                if paragraph.strip():
                    document.add_paragraph(paragraph.strip())
        with atomic_output_path(target) as temporary:
            document.save(temporary)
        verified = verify_written_file(target)
        return {
            "action": action,
            "completed": True,
            "output_path": str(target),
            **verified,
            "pages": len(reader.pages),
            "note": "Text content was converted; complex PDF layout may not be preserved.",
        }
    if extension in {".mp4", ".mov", ".mkv", ".webm", ".avi"} and action == "trim_video":
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("FFmpeg is required for video trimming. Install FFmpeg and add it to PATH.")
        start = bounded_number(start_seconds, minimum=0, maximum=86_400, field="start_seconds")
        end = bounded_number(end_seconds, minimum=0.1, maximum=86_400, field="end_seconds")
        if end <= start:
            raise ValueError("end_seconds must be greater than start_seconds")
        if end - start > 3_600:
            raise ValueError("A single trim operation cannot exceed 60 minutes")
        target = _output_path(source, output_path, "_trimmed", source.suffix)
        _write_guard(target, confirmed, overwrite)
        with atomic_output_path(target) as temporary:
            run_command([
                ffmpeg, "-y", "-ss", f"{start:g}", "-to", f"{end:g}",
                "-i", str(source), "-map", "0", "-c", "copy", str(temporary),
            ], timeout=120)
        verified = verify_written_file(target)
        return {
            "action": action,
            "completed": True,
            "output_path": str(target),
            **verified,
            "start_seconds": start,
            "end_seconds": end,
        }
    raise ValueError("The requested action is not supported for this file type")


async def file_processor(
    action: str, path: str, output_path: str = "", width: int | None = None,
    height: int | None = None, quality: int = 85, column: str = "", value: str = "",
    descending: bool = False, confirmed: bool = False, overwrite: bool = False,
    start_seconds: float = 0, end_seconds: float = 0,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        _file_processor_sync, action, path, output_path, width, height, quality, column, value,
        descending, confirmed, overwrite, start_seconds, end_seconds,
    )


def register_processor_tools(registry: ToolRegistry) -> None:
    registry.register(ToolDefinition(
        name="game_updater",
        description="List Steam games/status or request an install/update through Steam. Install/update requires confirmation.",
        parameters={"type": "object", "properties": {
            "action": {"type": "string", "enum": ["list", "status", "update", "install"]},
            "game_name": {"type": "string"}, "app_id": {"type": "string"}, "confirmed": {"type": "boolean", "default": False},
        }, "required": ["action"], "additionalProperties": False}, handler=game_updater,
    ))
    registry.register(ToolDefinition(
        name="flight_finder",
        description="Build and optionally open a Google Flights search from validated airport codes and dates.",
        parameters={"type": "object", "properties": {
            "origin": {"type": "string"}, "destination": {"type": "string"}, "departure_date": {"type": "string"}, "return_date": {"type": "string"},
            "adults": {"type": "integer", "minimum": 1, "maximum": 9, "default": 1},
            "travel_class": {"type": "string", "enum": ["economy", "premium_economy", "business", "first"], "default": "economy"},
            "open_browser": {"type": "boolean", "default": True},
        }, "required": ["origin", "destination", "departure_date"], "additionalProperties": False}, handler=flight_finder,
    ))
    registry.register(ToolDefinition(
        name="file_processor",
        description="Perform bounded deterministic processing for text, JSON, CSV, Excel, image, PDF, and video files under the user profile. Supports verified PDF-to-Word output and FFmpeg video trimming. Never executes generated code.",
        parameters={"type": "object", "properties": {
            "action": {"type": "string", "enum": ["info", "extract_text", "word_count", "validate", "format", "stats", "filter", "sort", "image_info", "resize", "compress", "convert", "pdf_info", "pdf_to_word", "xlsx_stats", "trim_video"]},
            "path": {"type": "string"}, "output_path": {"type": "string"}, "width": {"type": "integer"}, "height": {"type": "integer"},
            "quality": {"type": "integer", "minimum": 20, "maximum": 100, "default": 85}, "column": {"type": "string"}, "value": {"type": "string"},
            "descending": {"type": "boolean", "default": False}, "start_seconds": {"type": "number", "minimum": 0}, "end_seconds": {"type": "number", "minimum": 0.1}, "confirmed": {"type": "boolean", "default": False}, "overwrite": {"type": "boolean", "default": False},
        }, "required": ["action", "path"], "additionalProperties": False}, handler=file_processor,
    ))

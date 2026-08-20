from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.tools.registry import ToolDefinition, ToolRegistry
from backend.app.tools.safety import (
    atomic_output_path,
    atomic_write_text,
    bounded_text,
    require_confirmation,
    require_optional_dependency,
    resolve_user_path,
    verify_written_file,
)

_MAX_SECTIONS = 100
_MAX_ROWS = 10_000
_MAX_CELLS = 100_000


def _slug(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "", value).strip().replace(" ", "_")[:80]
    return cleaned or fallback


def _document_output(output_path: str, title: str, extension: str) -> Path:
    target = (
        resolve_user_path(output_path)
        if output_path
        else resolve_user_path(f"Documents/Arix/{_slug(title, 'document')}{extension}")
    )
    if target.suffix.casefold() != extension:
        raise ValueError(f"output_path must end in {extension}")
    return target


def _prepare_output(target: Path, confirmed: bool, overwrite: bool) -> None:
    if target.exists():
        require_confirmation("overwrite the existing document", confirmed and overwrite)
    target.parent.mkdir(parents=True, exist_ok=True)


def _presentation_builder_sync(
    title: str,
    slides: list[dict[str, Any]],
    output_path: str,
    confirmed: bool,
    overwrite: bool,
) -> dict[str, Any]:
    heading = bounded_text(title, limit=200, field="title")
    if not 1 <= len(slides) <= 50:
        raise ValueError("slides must contain between 1 and 50 slides")
    pptx = require_optional_dependency("pptx", "pip install python-pptx")
    target = _document_output(output_path, heading, ".pptx")
    _prepare_output(target, confirmed, overwrite)
    presentation = pptx.Presentation()
    presentation.core_properties.title = heading
    presentation.core_properties.author = "Arix AI"
    for index, item in enumerate(slides):
        slide_title = bounded_text(item.get("title", f"Slide {index + 1}"), limit=200, field="slide title")
        bullets = [str(value).strip()[:1_000] for value in item.get("bullets", []) if str(value).strip()][:20]
        layout = presentation.slide_layouts[0 if index == 0 else 1]
        slide = presentation.slides.add_slide(layout)
        slide.shapes.title.text = slide_title
        if len(slide.placeholders) > 1:
            body = slide.placeholders[1]
            if index == 0 and item.get("subtitle"):
                body.text = str(item["subtitle"])[:500]
            elif bullets:
                body.text = bullets[0]
                for bullet in bullets[1:]:
                    body.text_frame.add_paragraph().text = bullet
    with atomic_output_path(target) as temporary:
        presentation.save(temporary)
    verified = verify_written_file(target)
    return {
        "created": True,
        "completed": True,
        **verified,
        "slides": len(slides),
        "title": heading,
    }


async def presentation_builder(
    title: str,
    slides: list[dict[str, Any]],
    output_path: str = "",
    confirmed: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        _presentation_builder_sync, title, slides, output_path, confirmed, overwrite
    )


def _spreadsheet_builder_sync(
    title: str,
    sheets: list[dict[str, Any]],
    output_path: str,
    confirmed: bool,
    overwrite: bool,
) -> dict[str, Any]:
    heading = bounded_text(title, limit=200, field="title")
    if not 1 <= len(sheets) <= 20:
        raise ValueError("sheets must contain between 1 and 20 worksheets")
    openpyxl = require_optional_dependency("openpyxl", "pip install openpyxl")
    styles = require_optional_dependency("openpyxl.styles", "pip install openpyxl")
    target = _document_output(output_path, heading, ".xlsx")
    _prepare_output(target, confirmed, overwrite)
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    total_cells = 0
    for index, item in enumerate(sheets):
        name = re.sub(r"[\\/*?:\[\]]", "", str(item.get("name", f"Sheet {index + 1}")))[:31] or f"Sheet {index + 1}"
        if name in workbook.sheetnames:
            name = f"{name[:27]}_{index + 1}"
        worksheet = workbook.create_sheet(name)
        rows = item.get("rows", [])
        if not isinstance(rows, list) or len(rows) > _MAX_ROWS:
            raise ValueError("each worksheet rows value must be a list of at most 10,000 rows")
        for row in rows:
            values = list(row) if isinstance(row, (list, tuple)) else [row]
            total_cells += len(values)
            if total_cells > _MAX_CELLS:
                raise ValueError("workbook exceeds the 100,000-cell limit")
            worksheet.append([value if isinstance(value, (str, int, float, bool, type(None))) else str(value) for value in values[:200]])
        if rows:
            for cell in worksheet[1]:
                cell.font = styles.Font(bold=True, color="FFFFFF")
                cell.fill = styles.PatternFill("solid", fgColor="2563EB")
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions
        for column in worksheet.columns:
            letter = column[0].column_letter
            worksheet.column_dimensions[letter].width = min(50, max(10, *(len(str(cell.value or "")) + 2 for cell in column[:100])))
    workbook.properties.title = heading
    workbook.properties.creator = "Arix AI"
    with atomic_output_path(target) as temporary:
        workbook.save(temporary)
    verified = verify_written_file(target)
    return {
        "created": True,
        "completed": True,
        **verified,
        "sheets": len(sheets),
        "cells": total_cells,
        "title": heading,
    }


async def spreadsheet_builder(
    title: str,
    sheets: list[dict[str, Any]],
    output_path: str = "",
    confirmed: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        _spreadsheet_builder_sync, title, sheets, output_path, confirmed, overwrite
    )


def _word_document_sync(
    title: str,
    sections: list[dict[str, Any]],
    output_path: str,
    author: str,
    confirmed: bool,
    overwrite: bool,
) -> dict[str, Any]:
    heading = bounded_text(title, limit=200, field="title")
    if len(sections) > _MAX_SECTIONS:
        raise ValueError("sections cannot exceed 100 items")
    docx = require_optional_dependency("docx", "pip install python-docx")
    target = _document_output(output_path, heading, ".docx")
    _prepare_output(target, confirmed, overwrite)
    document = docx.Document()
    document.core_properties.title = heading
    document.core_properties.author = (author.strip()[:200] or "Arix AI")
    document.add_heading(heading, level=0)
    for item in sections:
        section_title = str(item.get("heading", "")).strip()[:300]
        if section_title:
            document.add_heading(section_title, level=max(1, min(9, int(item.get("level", 1)))))
        text = str(item.get("text", ""))[:50_000]
        if text:
            for paragraph in text.split("\n\n"):
                if paragraph.strip():
                    document.add_paragraph(paragraph.strip())
        for bullet in [str(value).strip()[:2_000] for value in item.get("bullets", [])][:100]:
            if bullet:
                document.add_paragraph(bullet, style="List Bullet")
    with atomic_output_path(target) as temporary:
        document.save(temporary)
    verified = verify_written_file(target)
    return {
        "created": True,
        "completed": True,
        **verified,
        "sections": len(sections),
        "title": heading,
    }


async def word_document(
    title: str,
    sections: list[dict[str, Any]],
    output_path: str = "",
    author: str = "Arix AI",
    confirmed: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        _word_document_sync, title, sections, output_path, author, confirmed, overwrite
    )


def _pdf_document_sync(
    title: str,
    sections: list[dict[str, Any]],
    output_path: str,
    author: str,
    confirmed: bool,
    overwrite: bool,
) -> dict[str, Any]:
    heading = bounded_text(title, limit=200, field="title")
    if len(sections) > _MAX_SECTIONS:
        raise ValueError("sections cannot exceed 100 items")
    platypus = require_optional_dependency("reportlab.platypus", "pip install reportlab")
    styles_module = require_optional_dependency("reportlab.lib.styles", "pip install reportlab")
    pagesizes = require_optional_dependency("reportlab.lib.pagesizes", "pip install reportlab")
    target = _document_output(output_path, heading, ".pdf")
    _prepare_output(target, confirmed, overwrite)
    styles = styles_module.getSampleStyleSheet()
    story = [platypus.Paragraph(heading, styles["Title"]), platypus.Spacer(1, 18)]
    for item in sections:
        section_title = str(item.get("heading", "")).strip()[:300]
        if section_title:
            story.append(platypus.Paragraph(section_title, styles["Heading2"]))
        text = str(item.get("text", ""))[:50_000]
        for paragraph in text.split("\n\n"):
            if paragraph.strip():
                escaped = paragraph.strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                story.extend([platypus.Paragraph(escaped, styles["BodyText"]), platypus.Spacer(1, 8)])
        for bullet in [str(value).strip()[:2_000] for value in item.get("bullets", [])][:100]:
            if bullet:
                escaped = bullet.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                story.append(platypus.Paragraph(f"• {escaped}", styles["BodyText"]))
    with atomic_output_path(target) as temporary:
        document = platypus.SimpleDocTemplate(
            str(temporary),
            pagesize=pagesizes.LETTER,
            title=heading,
            author=author.strip()[:200] or "Arix AI",
        )
        document.build(story)
    verified = verify_written_file(target)
    return {
        "created": True,
        "completed": True,
        **verified,
        "sections": len(sections),
        "title": heading,
    }


async def pdf_document(
    title: str,
    sections: list[dict[str, Any]],
    output_path: str = "",
    author: str = "Arix AI",
    confirmed: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        _pdf_document_sync, title, sections, output_path, author, confirmed, overwrite
    )


def _task_store() -> Path:
    target = Path.home() / "AppData" / "Local" / "Arix" / "agent_tasks.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _load_tasks() -> list[dict[str, Any]]:
    path = _task_store()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return payload if isinstance(payload, list) else []


def _save_tasks(tasks: list[dict[str, Any]]) -> None:
    path = _task_store()
    atomic_write_text(path, json.dumps(tasks, ensure_ascii=False, indent=2))
    verify_written_file(path, minimum_bytes=2)


def _agent_task_sync(
    action: str,
    task_id: str,
    title: str,
    description: str,
    steps: list[str] | None,
    status: str,
    confirmed: bool,
) -> dict[str, Any]:
    tasks = _load_tasks()
    if action == "list":
        return {"action": action, "tasks": tasks[-200:], "count": len(tasks)}
    if action == "create":
        item = {
            "id": uuid.uuid4().hex[:12],
            "title": bounded_text(title, limit=200, field="title"),
            "description": str(description).strip()[:5_000],
            "steps": [str(step).strip()[:500] for step in (steps or []) if str(step).strip()][:50],
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        tasks.append(item)
        _save_tasks(tasks[-1_000:])
        return {"action": action, "created": True, "task": item}
    selected = next((item for item in tasks if item.get("id") == task_id), None)
    if not selected:
        raise ValueError("No agent task matches task_id")
    if action == "get":
        return {"action": action, "task": selected}
    if action == "update":
        if status not in {"pending", "in_progress", "completed", "cancelled"}:
            raise ValueError("Unsupported task status")
        selected["status"] = status
        selected["updated_at"] = datetime.now(timezone.utc).isoformat()
        _save_tasks(tasks)
        return {"action": action, "updated": True, "task": selected}
    if action == "delete":
        require_confirmation("delete this agent task record", confirmed)
        tasks.remove(selected)
        _save_tasks(tasks)
        return {"action": action, "deleted": True, "task_id": task_id}
    raise ValueError("action must be create, list, get, update, or delete")


async def agent_task(
    action: str,
    task_id: str = "",
    title: str = "",
    description: str = "",
    steps: list[str] | None = None,
    status: str = "pending",
    confirmed: bool = False,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        _agent_task_sync, action, task_id, title, description, steps, status, confirmed
    )


def _terminate_process() -> None:
    os.kill(os.getpid(), signal.SIGTERM)


async def shutdown_arix(confirmed: bool = False, delay_seconds: float = 1.0) -> dict[str, Any]:
    require_confirmation("shut down the Arix backend", confirmed)
    delay = max(0.5, min(float(delay_seconds), 10.0))
    timer = threading.Timer(delay, _terminate_process)
    timer.daemon = True
    timer.start()
    return {"shutdown_scheduled": True, "delay_seconds": delay, "scope": "Arix backend"}


def register_document_tools(registry: ToolRegistry) -> None:
    section_schema = {"type": "object", "properties": {
        "heading": {"type": "string"}, "text": {"type": "string"},
        "bullets": {"type": "array", "items": {"type": "string"}, "maxItems": 100},
        "level": {"type": "integer", "minimum": 1, "maximum": 9},
    }, "additionalProperties": False}
    common_output = {
        "output_path": {"type": "string"}, "confirmed": {"type": "boolean", "default": False},
        "overwrite": {"type": "boolean", "default": False},
    }
    registry.register(ToolDefinition(
        name="presentation_builder",
        description="Create and verify a PowerPoint presentation from structured slide titles and bullets. output_path may use a Documents/... known-folder alias.",
        parameters={"type": "object", "properties": {"title": {"type": "string"}, "slides": {"type": "array", "minItems": 1, "maxItems": 50, "items": {"type": "object", "properties": {"title": {"type": "string"}, "subtitle": {"type": "string"}, "bullets": {"type": "array", "items": {"type": "string"}, "maxItems": 20}}, "additionalProperties": False}}, **common_output}, "required": ["title", "slides"], "additionalProperties": False},
        handler=presentation_builder,
    ))
    registry.register(ToolDefinition(
        name="spreadsheet_builder",
        description="Create and verify a formatted Excel workbook from structured worksheet rows. output_path may use a Documents/... known-folder alias.",
        parameters={"type": "object", "properties": {"title": {"type": "string"}, "sheets": {"type": "array", "minItems": 1, "maxItems": 20, "items": {"type": "object", "properties": {"name": {"type": "string"}, "rows": {"type": "array", "maxItems": _MAX_ROWS, "items": {"type": "array", "maxItems": 200}}}, "required": ["rows"], "additionalProperties": False}}, **common_output}, "required": ["title", "sheets"], "additionalProperties": False},
        handler=spreadsheet_builder,
    ))
    for name, description, handler in (
        ("word_document", "Create a Word document from structured sections.", word_document),
        ("pdf_document", "Create a PDF document from structured sections.", pdf_document),
    ):
        registry.register(ToolDefinition(
            name=name, description=description,
            parameters={"type": "object", "properties": {"title": {"type": "string"}, "sections": {"type": "array", "maxItems": _MAX_SECTIONS, "items": section_schema}, "author": {"type": "string"}, **common_output}, "required": ["title", "sections"], "additionalProperties": False},
            handler=handler,
        ))
    registry.register(ToolDefinition(
        name="agent_task",
        description="Create and track a structured local task record. This does not run arbitrary commands or claim autonomous execution.",
        parameters={"type": "object", "properties": {
            "action": {"type": "string", "enum": ["create", "list", "get", "update", "delete"]},
            "task_id": {"type": "string"}, "title": {"type": "string"}, "description": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "string"}, "maxItems": 50},
            "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"]},
            "confirmed": {"type": "boolean", "default": False},
        }, "required": ["action"], "additionalProperties": False}, handler=agent_task,
    ))
    registry.register(ToolDefinition(
        name="shutdown_arix",
        description="Gracefully request shutdown of the Arix backend. Requires explicit user confirmation.",
        parameters={"type": "object", "properties": {
            "confirmed": {"type": "boolean", "default": False},
            "delay_seconds": {"type": "number", "minimum": 0.5, "maximum": 10, "default": 1},
        }, "additionalProperties": False}, handler=shutdown_arix,
    ))

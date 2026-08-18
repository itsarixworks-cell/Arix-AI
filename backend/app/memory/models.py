from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

MemoryCategory = Literal[
    "identity", "preferences", "projects", "relationships", "wishes", "notes"
]
MemorySource = Literal["manager", "live_direct", "migration", "anchor"]

CATEGORY_COLORS: dict[str, str] = {
    "identity": "#48D9FF",
    "preferences": "#A77BFF",
    "projects": "#FFB55F",
    "relationships": "#FF6B9E",
    "wishes": "#61E7A8",
    "notes": "#8290A6",
}
ANCHOR_COLORS = {"ai_root": "#6E8BFF", "user_root": "#F3F7FF"}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class MemoryConnection(BaseModel):
    to: str
    relation: str = "related_to"
    weight: float = Field(default=0.5, ge=0.0, le=1.0)


class MemoryNode(BaseModel):
    id: str
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(default="", max_length=8000)
    category: MemoryCategory = "notes"
    color: str = CATEGORY_COLORS["notes"]
    size: float = Field(default=1.0, ge=0.25, le=12.0)
    connections: list[MemoryConnection] = Field(default_factory=list)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    created_at: str = Field(default_factory=utc_now)
    last_accessed: str = Field(default_factory=utc_now)
    access_count: int = Field(default=0, ge=0)
    source: MemorySource = "manager"
    archived: bool = False

    @field_validator("color", mode="before")
    @classmethod
    def fill_color(cls, value: str | None, info):
        return value or CATEGORY_COLORS.get(info.data.get("category", "notes"), CATEGORY_COLORS["notes"])


class TitleIndexEntry(BaseModel):
    title: str
    category: MemoryCategory
    color: str
    importance: float = 0.5
    last_accessed: str = Field(default_factory=utc_now)


class GraphSnapshot(BaseModel):
    nodes: dict[str, MemoryNode] = Field(default_factory=dict)
    edges: dict[str, dict[str, dict[str, float | str]]] = Field(default_factory=dict)
    title_index: dict[str, TitleIndexEntry] = Field(default_factory=dict)
    anchors: dict[str, bool] = Field(default_factory=lambda: {"ai_root": True, "user_root": True})


def anchor_nodes() -> dict[str, MemoryNode]:
    now = utc_now()
    return {
        "ai_root": MemoryNode(
            id="ai_root", title="Arix AI", summary="Permanent root for Arix knowledge.",
            color=ANCHOR_COLORS["ai_root"], size=8.0, importance=1.0,
            source="anchor", created_at=now, last_accessed=now,
        ),
        "user_root": MemoryNode(
            id="user_root", title="User", summary="Permanent root for user knowledge.",
            category="identity", color=ANCHOR_COLORS["user_root"], size=8.0,
            importance=1.0, source="anchor", created_at=now, last_accessed=now,
        ),
    }

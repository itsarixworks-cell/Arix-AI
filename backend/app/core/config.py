from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True, slots=True)
class Settings:
    host: str = os.getenv("ARIX_HOST", "127.0.0.1")
    port: int = int(os.getenv("ARIX_PORT", "8765"))
    fallback_api_key: str = os.getenv("GEMINI_API_KEY", "")
    allowed_origins: tuple[str, ...] = tuple(
        value.strip()
        for value in os.getenv(
            "ARIX_ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
        ).split(",")
        if value.strip()
    )


settings = Settings()

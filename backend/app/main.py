from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.live import router as live_router
from backend.app.core.config import settings

app = FastAPI(
    title="Arix Local Bridge",
    version="0.1.0",
    description="Local-only bridge between the Arix Electron client and Gemini Live.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.include_router(live_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "arix-local-bridge", "version": app.version}

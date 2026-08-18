from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.live import router as live_router
from backend.app.api.memory import router as memory_router
from backend.app.core.config import settings
from backend.app.memory.runtime import create_memory_runtime


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.memory_runtime = await create_memory_runtime(
        settings.data_directory,
        firebase_database_url=settings.firebase_database_url,
        firebase_service_account=settings.firebase_service_account,
        firebase_service_account_json=settings.firebase_service_account_json,
    )
    yield
    await app.state.memory_runtime.close()


app = FastAPI(
    title="Arix Local Bridge",
    version="0.2.0",
    description="Local-only bridge between the Arix Electron client and Gemini Live.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.include_router(live_router)
app.include_router(memory_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "arix-local-bridge", "version": app.version}

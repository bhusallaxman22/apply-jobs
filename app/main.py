from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import ensure_storage_dirs, get_settings
from app.db import init_db
from app.routes import dashboard, jobs, profiles, runs, sources
from app.schemas import HealthResponse


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_storage_dirs()
    init_db()
    yield


settings = get_settings()
app = FastAPI(title="Job Agent", version="0.1.0", lifespan=lifespan)
static_root = Path(__file__).resolve().parent / "static"

app.mount("/static", StaticFiles(directory=static_root), name="static")

app.include_router(dashboard.router)
app.include_router(profiles.router, prefix="/profiles", tags=["profiles"])
app.include_router(sources.router, prefix="/sources", tags=["sources"])
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
app.include_router(runs.router, prefix="/runs", tags=["runs"])


@app.get("/health", response_model=HealthResponse)
def healthcheck() -> HealthResponse:
    return HealthResponse(status="ok", environment=settings.app_env)

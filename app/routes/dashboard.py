from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse

router = APIRouter()

STATIC_DIR = Path(__file__).resolve().parents[1] / "static" / "dashboard"


@router.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/dashboard", status_code=307)


@router.get("/dashboard", include_in_schema=False)
def dashboard_index():
    return FileResponse(STATIC_DIR / "index.html")

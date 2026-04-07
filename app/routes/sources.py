from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.job_sources import create_or_get_source, serialize_source, sync_job_source
from app.models import JobSource
from app.schemas import JobSourceCreate, JobSourceRead, JobSourceSyncRead

router = APIRouter()


@router.get("", response_model=list[JobSourceRead])
def list_sources(session: Session = Depends(get_session)) -> list[JobSourceRead]:
    sources = session.query(JobSource).order_by(JobSource.created_at.desc()).all()
    return [serialize_source(source) for source in sources]


@router.post("", response_model=JobSourceSyncRead | JobSourceRead)
async def create_source(payload: JobSourceCreate, session: Session = Depends(get_session)):
    source = await create_or_get_source(session, payload)
    session.commit()
    session.refresh(source)
    if payload.auto_sync:
        return await sync_job_source(session, source)
    return serialize_source(source)


@router.post("/{source_id}/sync", response_model=JobSourceSyncRead)
async def sync_source(source_id: str, session: Session = Depends(get_session)) -> JobSourceSyncRead:
    source = session.get(JobSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Job source not found.")
    return await sync_job_source(session, source)

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent.runner import execute_run
from app.db import get_session
from app.models import Job, Profile, Run
from app.schemas import RunApproval, RunCreate, RunRead

router = APIRouter()


def _serialize_run(run: Run) -> RunRead:
    return RunRead(
        id=run.id,
        job_id=run.job_id,
        profile_id=run.profile_id,
        status=run.status,
        platform=run.platform,
        extracted_fields=run.extracted_fields,
        decisions=run.decisions,
        artifacts=run.artifacts,
        pending_review=run.pending_review,
        result=run.result,
        error_message=run.error_message,
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


@router.get("", response_model=list[RunRead])
def list_runs(session: Session = Depends(get_session)) -> list[RunRead]:
    runs = session.query(Run).order_by(Run.created_at.desc()).all()
    return [_serialize_run(run) for run in runs]


@router.get("/{run_id}", response_model=RunRead)
def get_run(run_id: str, session: Session = Depends(get_session)) -> RunRead:
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return _serialize_run(run)


@router.post("", response_model=RunRead)
def create_run(
    payload: RunCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> RunRead:
    profile = session.get(Profile, payload.profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found.")

    if payload.job_id:
        job = session.get(Job, payload.job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found.")
    else:
        job = Job(url=payload.job_url)
        session.add(job)
        session.flush()

    run = Run(job_id=job.id, profile_id=profile.id)
    session.add(run)
    session.commit()
    session.refresh(run)

    background_tasks.add_task(execute_run, run.id)
    return _serialize_run(run)


@router.post("/{run_id}/approve", response_model=RunRead)
def approve_run(
    run_id: str,
    payload: RunApproval,
    session: Session = Depends(get_session),
) -> RunRead:
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    run.status = "approved"
    run.pending_review = {
        **(run.pending_review or {}),
        "approved": True,
        "notes": payload.notes,
    }
    session.commit()
    session.refresh(run)
    return _serialize_run(run)


@router.post("/{run_id}/reject", response_model=RunRead)
def reject_run(
    run_id: str,
    payload: RunApproval,
    session: Session = Depends(get_session),
) -> RunRead:
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    run.status = "rejected"
    run.pending_review = {
        **(run.pending_review or {}),
        "approved": False,
        "notes": payload.notes,
    }
    session.commit()
    session.refresh(run)
    return _serialize_run(run)

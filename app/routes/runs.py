from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.agent.live_sessions import signal_live_run_cancel, signal_live_run_resume
from app.agent.runner import execute_run, submit_approved_run
from app.config import get_settings
from app.db import get_session
from app.models import Job, Profile, Run
from app.schemas import BulkRunCreate, BulkRunRead, RunApproval, RunCreate, RunRead

router = APIRouter()
logger = logging.getLogger(__name__)

ACTIVE_RUN_STATUSES = {"queued", "running", "review", "submitting", "captcha_required"}
STALE_SUBMITTING_TIMEOUT = timedelta(minutes=10)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_storage_file(path_value: str | None) -> Path:
    if not path_value:
        raise HTTPException(status_code=404, detail="Artifact not available.")

    resolved_path = Path(path_value).expanduser().resolve()
    storage_root = get_settings().storage_path

    try:
        resolved_path.relative_to(storage_root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Artifact path is outside the storage root.") from exc

    if not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Artifact file not found.")

    return resolved_path


def _get_review_resume_path(run: Run) -> Path:
    tailored_resume = (
        (run.pending_review or {}).get("tailored_resume")
        or (run.artifacts or {}).get("tailored_resume")
        or {}
    )
    pdf_path = tailored_resume.get("pdf_path")
    if not pdf_path:
        raise HTTPException(status_code=404, detail="Tailored resume not available for this run.")
    return _resolve_storage_file(pdf_path)


def _get_review_screenshot_path(run: Run) -> Path:
    screenshot_path = (run.artifacts or {}).get("latest_screenshot")
    if not screenshot_path:
        raise HTTPException(status_code=404, detail="Screenshot not available for this run.")
    return _resolve_storage_file(screenshot_path)


def _get_progress_screenshot_path(run: Run, screenshot_index: int) -> Path:
    screenshots = (run.artifacts or {}).get("progress_screenshots") or []
    if screenshot_index < 0 or screenshot_index >= len(screenshots):
        raise HTTPException(status_code=404, detail="Progress screenshot not found.")
    screenshot_path = screenshots[screenshot_index].get("path")
    if not screenshot_path:
        raise HTTPException(status_code=404, detail="Progress screenshot path not available.")
    return _resolve_storage_file(screenshot_path)


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


def _recover_stale_submitting_runs(session: Session) -> None:
    cutoff = utc_now() - STALE_SUBMITTING_TIMEOUT
    stale_runs = (
        session.query(Run)
        .filter(Run.status == "submitting", Run.updated_at < cutoff)
        .all()
    )
    if not stale_runs:
        return

    for run in stale_runs:
        job = session.get(Job, run.job_id)
        message = (
            f"Automatic submit stalled for more than {int(STALE_SUBMITTING_TIMEOUT.total_seconds() // 60)} minutes and was returned to review."
        )
        run.status = "review"
        run.error_message = message
        run.pending_review = {
            **(run.pending_review or {}),
            "approved": True,
            "submission_error": message,
        }
        if job is not None:
            job.status = "review"
        logger.warning("Recovered stale submitting run %s back to review.", run.id)

    session.commit()


@router.get("", response_model=list[RunRead])
def list_runs(
    profile_id: str | None = None,
    job_id: str | None = None,
    session: Session = Depends(get_session),
) -> list[RunRead]:
    _recover_stale_submitting_runs(session)
    query = session.query(Run)
    if profile_id is not None:
        query = query.filter(Run.profile_id == profile_id)
    if job_id is not None:
        query = query.filter(Run.job_id == job_id)
    runs = query.order_by(Run.created_at.desc()).all()
    return [_serialize_run(run) for run in runs]


@router.get("/{run_id}", response_model=RunRead)
def get_run(run_id: str, session: Session = Depends(get_session)) -> RunRead:
    _recover_stale_submitting_runs(session)
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return _serialize_run(run)


@router.get("/{run_id}/review/resume")
def get_review_resume(run_id: str, session: Session = Depends(get_session)) -> FileResponse:
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    resume_path = _get_review_resume_path(run)
    return FileResponse(
        resume_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{resume_path.name}"'},
    )


@router.get("/{run_id}/review/screenshot")
def get_review_screenshot(run_id: str, session: Session = Depends(get_session)) -> FileResponse:
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    screenshot_path = _get_review_screenshot_path(run)
    return FileResponse(
        screenshot_path,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="{screenshot_path.name}"'},
    )


@router.get("/{run_id}/progress-screenshots/{screenshot_index}")
def get_progress_screenshot(run_id: str, screenshot_index: int, session: Session = Depends(get_session)) -> FileResponse:
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    screenshot_path = _get_progress_screenshot_path(run, screenshot_index)
    return FileResponse(
        screenshot_path,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="{screenshot_path.name}"'},
    )


def _create_run_record(
    *,
    session: Session,
    background_tasks: BackgroundTasks,
    profile: Profile,
    job: Job,
) -> Run:
    run = Run(job_id=job.id, profile_id=profile.id)
    session.add(run)
    session.commit()
    session.refresh(run)
    background_tasks.add_task(execute_run, run.id)
    return run


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
        job = Job(
            url=payload.job_url,
            company=payload.company,
            title=payload.job_title,
            description=payload.job_description,
        )
        session.add(job)
        session.flush()
        session.commit()
        session.refresh(job)

    run = _create_run_record(session=session, background_tasks=background_tasks, profile=profile, job=job)
    return _serialize_run(run)


@router.post("/bulk", response_model=BulkRunRead)
def create_bulk_runs(
    payload: BulkRunCreate,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> BulkRunRead:
    profile = session.get(Profile, payload.profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found.")

    jobs = session.query(Job).filter(Job.id.in_(payload.job_ids)).all()
    jobs_by_id = {job.id: job for job in jobs}
    created_runs: list[RunRead] = []
    skipped_jobs: list[dict[str, str]] = []

    for job_id in payload.job_ids:
        job = jobs_by_id.get(job_id)
        if job is None:
            skipped_jobs.append({"job_id": job_id, "reason": "Job not found."})
            continue
        if job.availability == "closed":
            skipped_jobs.append({"job_id": job_id, "reason": "Job is closed."})
            continue

        existing = (
            session.query(Run)
            .filter(
                Run.profile_id == profile.id,
                Run.job_id == job.id,
                Run.status.in_(ACTIVE_RUN_STATUSES),
            )
            .order_by(Run.created_at.desc())
            .first()
        )
        if existing is not None:
            skipped_jobs.append({"job_id": job.id, "reason": f"Existing active run: {existing.status}."})
            continue

        created_run = _create_run_record(
            session=session,
            background_tasks=background_tasks,
            profile=profile,
            job=job,
        )
        created_runs.append(_serialize_run(created_run))

    return BulkRunRead(
        requested_count=len(payload.job_ids),
        created_count=len(created_runs),
        skipped_count=len(skipped_jobs),
        created_runs=created_runs,
        skipped_jobs=skipped_jobs,
    )


@router.post("/{run_id}/approve", response_model=RunRead)
def approve_run(
    run_id: str,
    payload: RunApproval,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> RunRead:
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    if run.status != "review":
        raise HTTPException(status_code=409, detail="Only runs in review status can be approved.")

    job = session.get(Job, run.job_id)
    logger.info(
        "Approving review run %s for job %s and queueing automatic submission.",
        run.id,
        run.job_id,
    )
    run.status = "submitting"
    run.pending_review = {
        **(run.pending_review or {}),
        "approved": True,
        "notes": payload.notes,
        "submission_error": None,
    }
    run.error_message = None
    run.finished_at = None
    if job is not None:
        job.status = run.status
    session.commit()
    session.refresh(run)
    background_tasks.add_task(submit_approved_run, run.id)
    return _serialize_run(run)


@router.post("/{run_id}/captcha/resume", response_model=RunRead)
async def resume_captcha_run(
    run_id: str,
    payload: RunApproval,
    session: Session = Depends(get_session),
) -> RunRead:
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    if run.status != "captcha_required":
        raise HTTPException(status_code=409, detail="Only runs waiting on CAPTCHA can be resumed.")

    if payload.notes is not None:
        run.pending_review = {
            **(run.pending_review or {}),
            "notes": payload.notes,
        }
        session.commit()
        session.refresh(run)

    if not signal_live_run_resume(run.id):
        raise HTTPException(
            status_code=409,
            detail="No live CAPTCHA session is available for this run. Requeue the run after enabling browser desktop access.",
        )

    logger.info("Resume signal sent for CAPTCHA-blocked run %s.", run.id)
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
    if run.status not in {"review", "captcha_required"}:
        raise HTTPException(status_code=409, detail="Only runs in review or captcha_required status can be rejected.")

    job = session.get(Job, run.job_id)
    logger.info("Rejecting review run %s for job %s.", run.id, run.job_id)
    run.status = "rejected"
    run.pending_review = {
        **(run.pending_review or {}),
        "approved": False,
        "notes": payload.notes,
    }
    if job is not None:
        job.status = run.status
    session.commit()
    session.refresh(run)
    signal_live_run_cancel(run.id)
    return _serialize_run(run)

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Job
from app.schemas import JobCreate, JobRead

router = APIRouter()


def _serialize_job(job: Job) -> JobRead:
    return JobRead(
        id=job.id,
        source_id=job.source_id,
        external_job_id=job.external_job_id,
        url=job.url,
        company=job.company,
        title=job.title,
        description=job.description,
        location=job.location,
        employment_type=job.employment_type,
        availability=job.availability,
        platform=job.platform,
        status=job.status,
        source_metadata=job.source_metadata,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("", response_model=list[JobRead])
def list_jobs(
    source_id: str | None = None,
    availability: str | None = None,
    session: Session = Depends(get_session),
) -> list[JobRead]:
    query = session.query(Job)
    if source_id is not None:
        query = query.filter(Job.source_id == source_id)
    if availability is not None:
        query = query.filter(Job.availability == availability)
    jobs = query.order_by(Job.created_at.desc()).all()
    return [_serialize_job(job) for job in jobs]


@router.post("", response_model=JobRead)
def create_job(payload: JobCreate, session: Session = Depends(get_session)) -> JobRead:
    job = Job(
        url=payload.url,
        company=payload.company,
        title=payload.title,
        description=payload.description,
        location=payload.location,
        employment_type=payload.employment_type,
        availability="open",
        source_metadata={},
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return _serialize_job(job)

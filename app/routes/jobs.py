from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Job
from app.schemas import JobCreate, JobRead

router = APIRouter()


def _serialize_job(job: Job) -> JobRead:
    return JobRead(
        id=job.id,
        url=job.url,
        company=job.company,
        platform=job.platform,
        status=job.status,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("", response_model=list[JobRead])
def list_jobs(session: Session = Depends(get_session)) -> list[JobRead]:
    jobs = session.query(Job).order_by(Job.created_at.desc()).all()
    return [_serialize_job(job) for job in jobs]


@router.post("", response_model=JobRead)
def create_job(payload: JobCreate, session: Session = Depends(get_session)) -> JobRead:
    job = Job(url=payload.url, company=payload.company)
    session.add(job)
    session.commit()
    session.refresh(job)
    return _serialize_job(job)

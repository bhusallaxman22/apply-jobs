from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session, selectinload

from app.answer_bank import normalize_prompt
from app.config import get_settings
from app.db import get_session
from app.models import AnswerEntry, Profile
from app.schemas import AnswerEntryCreate, ProfileCreate, ProfileRead, ProfileUpdate

router = APIRouter()


def _profile_query(session: Session):
    return session.query(Profile).options(selectinload(Profile.answers))


def _serialize_profile(profile: Profile) -> ProfileRead:
    return ProfileRead(
        id=profile.id,
        name=profile.name,
        data=profile.data,
        resume_path=profile.resume_path,
        answers=[
            {
                "id": answer.id,
                "prompt": answer.prompt,
                "answer": answer.answer,
                "safe_to_autofill": answer.safe_to_autofill,
                "created_at": answer.created_at,
                "updated_at": answer.updated_at,
            }
            for answer in profile.answers
        ],
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.get("", response_model=list[ProfileRead])
def list_profiles(session: Session = Depends(get_session)) -> list[ProfileRead]:
    return [_serialize_profile(profile) for profile in _profile_query(session).all()]


@router.post("", response_model=ProfileRead)
def create_profile(payload: ProfileCreate, session: Session = Depends(get_session)) -> ProfileRead:
    profile = Profile(name=payload.name, data=payload.data)
    session.add(profile)
    session.flush()

    for answer in payload.answers:
        session.add(
            AnswerEntry(
                profile_id=profile.id,
                prompt=answer.prompt,
                normalized_prompt=normalize_prompt(answer.prompt),
                answer=answer.answer,
                safe_to_autofill=answer.safe_to_autofill,
            )
        )

    session.commit()
    session.refresh(profile)
    profile = _profile_query(session).filter(Profile.id == profile.id).one()
    return _serialize_profile(profile)


@router.get("/{profile_id}", response_model=ProfileRead)
def get_profile(profile_id: str, session: Session = Depends(get_session)) -> ProfileRead:
    profile = _profile_query(session).filter(Profile.id == profile_id).one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return _serialize_profile(profile)


@router.put("/{profile_id}", response_model=ProfileRead)
def update_profile(profile_id: str, payload: ProfileUpdate, session: Session = Depends(get_session)) -> ProfileRead:
    profile = _profile_query(session).filter(Profile.id == profile_id).one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found.")
    if payload.name is not None:
        profile.name = payload.name
    if payload.data is not None:
        profile.data = payload.data
    session.commit()
    session.refresh(profile)
    profile = _profile_query(session).filter(Profile.id == profile.id).one()
    return _serialize_profile(profile)


@router.post("/{profile_id}/answers", response_model=ProfileRead)
def add_profile_answer(
    profile_id: str,
    payload: AnswerEntryCreate,
    session: Session = Depends(get_session),
) -> ProfileRead:
    profile = _profile_query(session).filter(Profile.id == profile_id).one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found.")

    session.add(
        AnswerEntry(
            profile_id=profile.id,
            prompt=payload.prompt,
            normalized_prompt=normalize_prompt(payload.prompt),
            answer=payload.answer,
            safe_to_autofill=payload.safe_to_autofill,
        )
    )
    session.commit()
    profile = _profile_query(session).filter(Profile.id == profile.id).one()
    return _serialize_profile(profile)


@router.post("/{profile_id}/resume", response_model=ProfileRead)
def upload_resume(
    profile_id: str,
    resume: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> ProfileRead:
    profile = _profile_query(session).filter(Profile.id == profile_id).one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found.")

    settings = get_settings()
    suffix = Path(resume.filename or "resume.pdf").suffix or ".pdf"
    destination = settings.resumes_path / f"{profile.id}-{uuid4().hex}{suffix}"
    destination.write_bytes(resume.file.read())

    profile.resume_path = str(destination)
    updated_data = dict(profile.data or {})
    documents = dict(updated_data.get("documents", {}))
    documents["resume_pdf"] = str(destination)
    updated_data["documents"] = documents
    profile.data = updated_data
    session.commit()
    session.refresh(profile)
    profile = _profile_query(session).filter(Profile.id == profile.id).one()
    return _serialize_profile(profile)

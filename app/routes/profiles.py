from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session, selectinload

from app.answer_bank import normalize_prompt
from app.config import get_settings
from app.db import get_session
from app.models import AnswerEntry, Profile
from app.resume_customizer import create_resume_variant, extract_pdf_text, hydrate_profile_resume
from app.schemas import (
    AnswerEntryCreate,
    AnswerEntryUpdate,
    ProfileCreate,
    ProfileRead,
    ProfileUpdate,
    ResumeCustomizeRequest,
    ResumeVariantRead,
)

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


def _write_upload(destination: Path, uploaded_file: UploadFile) -> None:
    destination.write_bytes(uploaded_file.file.read())


def _update_profile_documents(profile: Profile, **updates) -> None:
    updated_data = dict(profile.data or {})
    documents = dict(updated_data.get("documents", {}))
    documents.update({key: value for key, value in updates.items() if value is not None})
    updated_data["documents"] = documents
    profile.data = updated_data


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


@router.put("/{profile_id}/answers/{answer_id}", response_model=ProfileRead)
def update_profile_answer(
    profile_id: str,
    answer_id: str,
    payload: AnswerEntryUpdate,
    session: Session = Depends(get_session),
) -> ProfileRead:
    profile = _profile_query(session).filter(Profile.id == profile_id).one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found.")

    answer = (
        session.query(AnswerEntry)
        .filter(AnswerEntry.id == answer_id, AnswerEntry.profile_id == profile.id)
        .one_or_none()
    )
    if answer is None:
        raise HTTPException(status_code=404, detail="Answer entry not found.")

    if payload.prompt is not None:
        answer.prompt = payload.prompt
        answer.normalized_prompt = normalize_prompt(payload.prompt)
    if payload.answer is not None:
        answer.answer = payload.answer
    if payload.safe_to_autofill is not None:
        answer.safe_to_autofill = payload.safe_to_autofill

    session.commit()
    profile = _profile_query(session).filter(Profile.id == profile.id).one()
    return _serialize_profile(profile)


@router.delete("/{profile_id}/answers/{answer_id}", response_model=ProfileRead)
def delete_profile_answer(
    profile_id: str,
    answer_id: str,
    session: Session = Depends(get_session),
) -> ProfileRead:
    profile = _profile_query(session).filter(Profile.id == profile_id).one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found.")

    answer = (
        session.query(AnswerEntry)
        .filter(AnswerEntry.id == answer_id, AnswerEntry.profile_id == profile.id)
        .one_or_none()
    )
    if answer is None:
        raise HTTPException(status_code=404, detail="Answer entry not found.")

    session.delete(answer)
    session.commit()
    profile = _profile_query(session).filter(Profile.id == profile.id).one()
    return _serialize_profile(profile)


@router.post("/{profile_id}/resume", response_model=ProfileRead)
def upload_resume(
    profile_id: str,
    resume: UploadFile = File(...),
    resume_markdown: UploadFile | None = File(None),
    resume_typst: UploadFile | None = File(None),
    resume_text: UploadFile | None = File(None),
    session: Session = Depends(get_session),
) -> ProfileRead:
    profile = _profile_query(session).filter(Profile.id == profile_id).one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found.")

    settings = get_settings()
    suffix = Path(resume.filename or "resume.pdf").suffix or ".pdf"
    destination = settings.resumes_path / f"{profile.id}-{uuid4().hex}{suffix}"
    _write_upload(destination, resume)

    profile.resume_path = str(destination)
    document_updates: dict[str, str] = {"resume_pdf": str(destination)}

    if resume_markdown is not None:
        markdown_path = settings.resumes_path / f"{profile.id}-{uuid4().hex}.md"
        _write_upload(markdown_path, resume_markdown)
        document_updates["resume_markdown_path"] = str(markdown_path)

    if resume_typst is not None:
        typst_path = settings.resumes_path / f"{profile.id}-{uuid4().hex}.typ"
        _write_upload(typst_path, resume_typst)
        document_updates["resume_typst_path"] = str(typst_path)

    if resume_text is not None:
        text_path = settings.resumes_path / f"{profile.id}-{uuid4().hex}.txt"
        _write_upload(text_path, resume_text)
        document_updates["resume_source_text_path"] = str(text_path)
    elif "resume_markdown_path" not in document_updates:
        try:
            extracted_text = extract_pdf_text(destination)
        except Exception:
            extracted_text = ""
        if extracted_text:
            text_path = settings.resumes_path / f"{profile.id}-{uuid4().hex}.txt"
            text_path.write_text(extracted_text, encoding="utf-8")
            document_updates["resume_source_text_path"] = str(text_path)

    _update_profile_documents(profile, **document_updates)
    session.commit()
    session.refresh(profile)
    profile = _profile_query(session).filter(Profile.id == profile.id).one()
    return _serialize_profile(profile)


@router.post("/{profile_id}/resume/customize", response_model=ResumeVariantRead)
async def customize_resume(
    profile_id: str,
    payload: ResumeCustomizeRequest,
    session: Session = Depends(get_session),
) -> ResumeVariantRead:
    profile = _profile_query(session).filter(Profile.id == profile_id).one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return await create_resume_variant(
        profile_id=profile.id,
        profile_data=hydrate_profile_resume(profile.data, resume_path=profile.resume_path),
        job_request=payload,
    )

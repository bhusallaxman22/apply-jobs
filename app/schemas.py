from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AnswerEntryCreate(BaseModel):
    prompt: str
    answer: str
    safe_to_autofill: bool = True


class AnswerEntryRead(AnswerEntryCreate):
    id: str
    created_at: datetime
    updated_at: datetime


class ProfileCreate(BaseModel):
    name: str
    data: dict[str, Any] = Field(default_factory=dict)
    answers: list[AnswerEntryCreate] = Field(default_factory=list)


class ProfileUpdate(BaseModel):
    name: str | None = None
    data: dict[str, Any] | None = None


class ProfileRead(BaseModel):
    id: str
    name: str
    data: dict[str, Any]
    resume_path: str | None
    answers: list[AnswerEntryRead]
    created_at: datetime
    updated_at: datetime


class JobCreate(BaseModel):
    url: str
    company: str | None = None
    title: str | None = None
    description: str | None = None
    location: str | None = None
    employment_type: str | None = None


class JobRead(BaseModel):
    id: str
    source_id: str | None
    external_job_id: str | None
    url: str
    company: str | None
    title: str | None
    description: str | None
    location: str | None
    employment_type: str | None
    availability: str
    platform: str
    status: str
    source_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class RunCreate(BaseModel):
    profile_id: str
    job_id: str | None = None
    job_url: str | None = None
    company: str | None = None
    job_title: str | None = None
    job_description: str | None = None

    @model_validator(mode="after")
    def validate_job_input(self) -> "RunCreate":
        if not self.job_id and not self.job_url:
            raise ValueError("Either job_id or job_url must be provided.")
        if self.job_id and self.job_url:
            raise ValueError("Provide job_id or job_url, not both.")
        return self


class BulkRunCreate(BaseModel):
    profile_id: str
    job_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_job_ids(self) -> "BulkRunCreate":
        if not self.job_ids:
            raise ValueError("job_ids must contain at least one job id.")
        return self


class BulkRunRead(BaseModel):
    requested_count: int
    created_count: int
    skipped_count: int
    created_runs: list["RunRead"]
    skipped_jobs: list[dict[str, str]]


class JobSourceCreate(BaseModel):
    name: str | None = None
    source_url: str | None = None
    platform: str | None = None
    source_token: str | None = None
    auto_sync: bool = True

    @model_validator(mode="after")
    def validate_source_input(self) -> "JobSourceCreate":
        if not self.source_url and not self.source_token:
            raise ValueError("Either source_url or source_token must be provided.")
        if self.platform is None and self.source_url is None:
            raise ValueError("platform is required when source_url is not provided.")
        return self


class JobSourceRead(BaseModel):
    id: str
    name: str
    source_url: str | None
    platform: str
    source_token: str
    last_sync_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class JobSourceSyncRead(BaseModel):
    source: JobSourceRead
    imported: int
    updated: int
    closed: int
    open_jobs: list[JobRead]


class RunApproval(BaseModel):
    notes: str | None = None


class RunRead(BaseModel):
    id: str
    job_id: str
    profile_id: str
    status: str
    platform: str
    extracted_fields: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    artifacts: dict[str, Any]
    pending_review: dict[str, Any]
    result: dict[str, Any]
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class HealthResponse(BaseModel):
    status: str
    environment: str


class PlannerAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thought: str = ""
    action: Literal["click", "type", "select", "extract", "done", "fail"]
    target: str
    value: str | None = None
    confidence: float = 0.0


class PageElement(BaseModel):
    label: str | None = None
    selector: str | None = None
    tag_name: str
    input_type: str | None = None
    name: str | None = None
    placeholder: str | None = None
    text: str | None = None
    value: str | None = None
    options: list[str] = Field(default_factory=list)
    disabled: bool = False


class PageState(BaseModel):
    url: str
    title: str
    visible_text: str
    elements: list[PageElement] = Field(default_factory=list)


class ExtractedField(BaseModel):
    label: str
    selector: str | None = None
    field_type: str
    name: str | None = None
    placeholder: str | None = None
    options: list[str] = Field(default_factory=list)
    current_value: str | None = None
    safe_to_autofill: bool = False
    profile_path: str | None = None
    answer_prompt: str | None = None


class AgentDecision(BaseModel):
    action: str
    target: str | None = None
    value: str | None = None
    source: str
    confidence: float | None = None
    note: str | None = None


class ResumeCustomizeRequest(BaseModel):
    job_url: str | None = None
    company: str | None = None
    job_title: str | None = None
    job_description: str


class TailoredSkillCategory(BaseModel):
    category: str
    items: list[str] = Field(default_factory=list)


class TailoredExperienceEntry(BaseModel):
    company: str
    role: str
    location: str | None = None
    dates: str | None = None
    bullets: list[str] = Field(default_factory=list)


class TailoredProjectEntry(BaseModel):
    name: str
    url: str | None = None
    bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class TailoredEducationEntry(BaseModel):
    institution: str
    degree: str | None = None
    dates: str | None = None
    details: list[str] = Field(default_factory=list)


class TailoredResumeDocument(BaseModel):
    summary: str
    skills: list[TailoredSkillCategory] = Field(default_factory=list)
    experience: list[TailoredExperienceEntry] = Field(default_factory=list)
    projects: list[TailoredProjectEntry] = Field(default_factory=list)
    education: list[TailoredEducationEntry] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)


class ResumeVariantRead(BaseModel):
    profile_id: str
    job_url: str | None = None
    company: str | None = None
    job_title: str | None = None
    markdown_path: str
    pdf_path: str
    source_path: str
    rendered_markdown: str
    review_notes: list[str] = Field(default_factory=list)
    generated_at: datetime


BulkRunRead.model_rebuild()

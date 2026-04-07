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


class JobRead(BaseModel):
    id: str
    url: str
    company: str | None
    platform: str
    status: str
    created_at: datetime
    updated_at: datetime


class RunCreate(BaseModel):
    profile_id: str
    job_id: str | None = None
    job_url: str | None = None

    @model_validator(mode="after")
    def validate_job_input(self) -> "RunCreate":
        if not self.job_id and not self.job_url:
            raise ValueError("Either job_id or job_url must be provided.")
        if self.job_id and self.job_url:
            raise ValueError("Provide job_id or job_url, not both.")
        return self


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

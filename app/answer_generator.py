from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.llm import LLMError, request_json_completion
from app.resume_customizer import ResumeCustomizationError, load_resume_source, profile_snapshot
from app.schemas import ExtractedField, PageState


class AnswerGenerationError(RuntimeError):
    pass


logger = logging.getLogger(__name__)


@dataclass
class GeneratedAnswer:
    answer: str
    confidence: float
    source_path: str
    note: str | None = None


def _answer_prompt(
    *,
    field: ExtractedField,
    page_state: PageState,
    profile_data: dict[str, Any],
    source_text: str,
    source_path: str,
) -> str:
    return f"""
Draft a truthful job application answer using only the supplied resume source and profile data.

Rules:
- Return valid JSON only.
- Never invent employers, dates, degrees, technologies, compensation, or achievements.
- Use first person.
- If the question cannot be answered from the supplied materials, set should_answer to false.
- Keep the answer concise and application-ready.
- Do not answer demographic, disability, veteran, ethnicity, gender, or other sensitive questions.
- If confidence is low, set should_answer to false.

Application field:
{json.dumps(
    {
        "label": field.label,
        "field_type": field.field_type,
        "placeholder": field.placeholder,
        "selector": field.selector,
    },
    indent=2,
)}

Job page context:
{json.dumps(
    {
        "url": page_state.url,
        "title": page_state.title,
        "visible_text": page_state.visible_text[:5000],
    },
    indent=2,
)}

Profile data:
{json.dumps(profile_snapshot(profile_data), indent=2)}

Resume source path:
{source_path}

Resume source content:
{source_text[:12000]}

Output schema:
{{
  "should_answer": true,
  "answer": "string",
  "confidence": 0.0,
  "reason": "short explanation"
}}
""".strip()


async def generate_long_form_answer(
    *,
    field: ExtractedField,
    page_state: PageState,
    profile_data: dict[str, Any],
) -> GeneratedAnswer:
    try:
        source_text, source_path = load_resume_source(profile_data)
    except ResumeCustomizationError as exc:
        raise AnswerGenerationError(str(exc)) from exc

    try:
        raw = await request_json_completion(
            system_prompt="You write accurate job application answers. Return JSON only.",
            user_prompt=_answer_prompt(
                field=field,
                page_state=page_state,
                profile_data=profile_data,
                source_text=source_text,
                source_path=source_path,
            ),
            temperature=0.2,
        )
    except LLMError as exc:
        raise AnswerGenerationError(str(exc)) from exc

    should_answer = bool(raw.get("should_answer"))
    answer = str(raw.get("answer") or "").strip()
    confidence_raw = raw.get("confidence", 0.0)
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.0
    note = str(raw.get("reason") or "").strip() or None

    if not should_answer or not answer or confidence < 0.55:
        raise AnswerGenerationError(note or "Model declined to answer from the supplied resume/profile context.")

    logger.info(
        "Generated AI answer for prompt %r with confidence %.2f using source %s.",
        field.label,
        confidence,
        source_path,
    )
    return GeneratedAnswer(
        answer=answer,
        confidence=max(0.0, min(confidence, 1.0)),
        source_path=source_path,
        note=note,
    )

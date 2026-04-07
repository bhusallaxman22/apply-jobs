from __future__ import annotations

import logging
from typing import Iterable

from app.agent.actions import click_target, fill_field
from app.agent.extractor import extract_form_schema
from app.agent.safety import is_safe_field, is_sensitive_label
from app.answer_generator import AnswerGenerationError, generate_long_form_answer
from app.answer_bank import best_answer_match
from app.models import AnswerEntry
from app.profile_store import lookup_profile_value
from app.schemas import PageState
from app.schemas import AgentDecision, ExtractedField

logger = logging.getLogger(__name__)


class GenericAdapter:
    name = "generic"
    apply_triggers = ("apply", "apply now", "apply for this job", "submit application")

    async def start_application(self, page) -> bool:
        for trigger in self.apply_triggers:
            try:
                await click_target(page, trigger)
                await page.wait_for_load_state("domcontentloaded")
                return True
            except Exception:
                continue
        return False

    async def extract_fields(self, page) -> list[ExtractedField]:
        return await extract_form_schema(page)

    async def autofill_fields(
        self,
        page,
        profile_data: dict,
        answers: Iterable[AnswerEntry],
    ) -> tuple[list[ExtractedField], list[dict], list[dict]]:
        fields = await self.extract_fields(page)
        page_state = await self._page_state(page)
        filled: list[dict] = []
        skipped: list[dict] = []

        for field in fields:
            if is_sensitive_label(field.label):
                skipped.append(
                    AgentDecision(
                        action="skip",
                        target=field.label,
                        source=self.name,
                        note="Sensitive question requires human review.",
                    ).model_dump()
                )
                continue

            profile_path, profile_value = lookup_profile_value_for_field(field, profile_data)
            if profile_value is not None and is_safe_field(field):
                try:
                    await fill_field(page, field, profile_value)
                    field.safe_to_autofill = True
                    field.profile_path = profile_path
                    filled.append(
                        AgentDecision(
                            action="fill",
                            target=field.label,
                            value=str(profile_value),
                            source=self.name,
                            note=f"Mapped from {profile_path}.",
                        ).model_dump()
                    )
                except Exception as exc:
                    skipped.append(
                        AgentDecision(
                            action="skip",
                            target=field.label,
                            source=self.name,
                            note=f"Autofill failed and was deferred to review: {exc}",
                        ).model_dump()
                    )
                continue

            if field.field_type in {"textarea", "text"}:
                answer = best_answer_match(field.label, answers)
                if answer and answer.safe_to_autofill and not is_sensitive_label(field.label):
                    try:
                        await fill_field(page, field, answer.answer)
                        field.safe_to_autofill = True
                        field.answer_prompt = answer.prompt
                        filled.append(
                            AgentDecision(
                                action="fill",
                                target=field.label,
                                value=answer.answer[:1000],
                                source="answer_bank",
                                note=f"Matched answer bank prompt: {answer.prompt}",
                            ).model_dump()
                        )
                    except Exception as exc:
                        skipped.append(
                            AgentDecision(
                                action="skip",
                                target=field.label,
                                source="answer_bank",
                                note=f"Answer bank fill failed and was deferred to review: {exc}",
                            ).model_dump()
                        )
                    continue

                try:
                    generated = await generate_long_form_answer(
                        field=field,
                        page_state=page_state,
                        profile_data=profile_data,
                    )
                    await fill_field(page, field, generated.answer)
                    field.safe_to_autofill = True
                    field.answer_prompt = f"AI-generated from {generated.source_path}"
                    filled.append(
                        AgentDecision(
                            action="fill",
                            target=field.label,
                            value=generated.answer[:1000],
                            source="llm_answer",
                            confidence=generated.confidence,
                            note=generated.note or f"Generated from selected profile resume: {generated.source_path}",
                        ).model_dump()
                    )
                    logger.info("AI-generated answer filled for field %r.", field.label)
                    continue
                except AnswerGenerationError as exc:
                    skipped.append(
                        AgentDecision(
                            action="skip",
                            target=field.label,
                            source="llm_answer",
                            note=f"AI answer generation deferred to review: {exc}",
                        ).model_dump()
                    )
                    logger.warning("AI answer generation deferred for field %r: %s", field.label, exc)
                except Exception as exc:
                    skipped.append(
                        AgentDecision(
                            action="skip",
                            target=field.label,
                            source="llm_answer",
                            note=f"AI answer generation failed and was deferred to review: {exc}",
                        ).model_dump()
                    )
                    logger.exception("AI answer generation failed for field %r.", field.label)
                continue

            skipped.append(
                AgentDecision(
                    action="skip",
                    target=field.label,
                    source=self.name,
                    note="No safe automatic answer found.",
                ).model_dump()
            )

        refreshed_fields = await self.extract_fields(page)
        return merge_field_metadata(fields, refreshed_fields), filled, skipped

    async def _page_state(self, page) -> PageState:
        from app.agent.extractor import extract_page_state

        return await extract_page_state(page)


def lookup_profile_value_for_field(field: ExtractedField, profile_data: dict) -> tuple[str | None, object]:
    candidates = [
        field.label,
        field.name,
        field.placeholder,
        field.selector,
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path, value = lookup_profile_value(candidate, profile_data)
        if value is not None:
            return path, value
    return None, None


def merge_field_metadata(original_fields: list[ExtractedField], refreshed_fields: list[ExtractedField]) -> list[ExtractedField]:
    original_by_key = {}
    for field in original_fields:
        key = field.selector or field.label or field.name or field.placeholder
        if key:
            original_by_key[key] = field

    merged: list[ExtractedField] = []
    for field in refreshed_fields:
        key = field.selector or field.label or field.name or field.placeholder
        original = original_by_key.get(key) if key else None
        if original is not None:
            field.safe_to_autofill = original.safe_to_autofill
            field.profile_path = original.profile_path
            field.answer_prompt = original.answer_prompt
        merged.append(field)
    return merged

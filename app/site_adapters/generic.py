from __future__ import annotations

from typing import Iterable

from app.agent.actions import click_target, fill_field
from app.agent.extractor import extract_form_schema
from app.agent.safety import is_safe_field, is_sensitive_label
from app.answer_bank import best_answer_match
from app.models import AnswerEntry
from app.profile_store import lookup_profile_value
from app.schemas import AgentDecision, ExtractedField


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

            profile_path, profile_value = lookup_profile_value(field.label, profile_data)
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

            skipped.append(
                AgentDecision(
                    action="skip",
                    target=field.label,
                    source=self.name,
                    note="No safe automatic answer found.",
                ).model_dump()
            )

        refreshed_fields = await self.extract_fields(page)
        return refreshed_fields, filled, skipped

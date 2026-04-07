from __future__ import annotations

import re
from pathlib import Path

from app.schemas import ExtractedField


def _target_regex(target: str) -> re.Pattern[str]:
    return re.compile(re.escape(target), re.IGNORECASE)


def _looks_like_selector(target: str) -> bool:
    return target.startswith(("#", ".", "[", "css=", "xpath=", "//")) or "[" in target


def _attribute_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _coerce_value(field: ExtractedField, value):
    if isinstance(value, bool):
        lowered_options = [option.lower() for option in field.options]
        if "yes" in lowered_options or "no" in lowered_options:
            return "Yes" if value else "No"
        return "Yes" if value else "No"
    return str(value)


async def resolve_locator(page, target: str):
    regex = _target_regex(target)
    locators = []

    if _looks_like_selector(target):
        locators.append(page.locator(target.replace("css=", "", 1)))

    locators.extend(
        [
            page.get_by_label(regex),
            page.get_by_placeholder(regex),
            page.get_by_role("button", name=regex),
            page.get_by_role("link", name=regex),
            page.get_by_text(regex),
            page.locator(f'[name="{_attribute_escape(target)}"]'),
        ]
    )

    for locator in locators:
        try:
            if await locator.count() > 0:
                return locator.first
        except Exception:
            continue
    raise ValueError(f"Could not resolve target: {target}")


async def click_target(page, target: str) -> None:
    locator = await resolve_locator(page, target)
    await locator.click(timeout=5_000)


async def type_target(page, target: str, value: str) -> None:
    locator = await resolve_locator(page, target)
    await locator.fill(str(value), timeout=5_000)


async def select_target(page, target: str, value: str) -> None:
    locator = await resolve_locator(page, target)
    text_value = str(value)
    try:
        await locator.select_option(label=text_value, timeout=5_000)
    except Exception:
        await locator.select_option(value=text_value.lower(), timeout=5_000)


async def fill_field(page, field: ExtractedField, value) -> None:
    target = field.selector or field.label or field.name or field.placeholder
    if not target:
        raise ValueError(f"Field has no usable target: {field.model_dump()}")

    coerced_value = _coerce_value(field, value)

    if field.field_type == "select":
        await select_target(page, target, coerced_value)
        return

    locator = await resolve_locator(page, target)
    input_type = (field.field_type or "").lower()
    if input_type == "file":
        candidate = Path(coerced_value)
        if not candidate.exists():
            raise FileNotFoundError(f"Resume path does not exist: {candidate}")
        await locator.set_input_files(str(candidate))
        return

    await locator.fill(coerced_value, timeout=5_000)

from __future__ import annotations

import re
from pathlib import Path

from rapidfuzz import fuzz

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


def _normalize_option_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _best_option_match(value: str, options: list[str]) -> str | None:
    normalized_value = _normalize_option_text(value)
    if not normalized_value:
        return None

    for option in options:
        if _normalize_option_text(option) == normalized_value:
            return option

    for option in options:
        normalized_option = _normalize_option_text(option)
        if normalized_value in normalized_option or normalized_option in normalized_value:
            return option

    best_option: str | None = None
    best_score = 0.0
    for option in options:
        score = fuzz.token_set_ratio(normalized_value, _normalize_option_text(option))
        if score > best_score:
            best_score = score
            best_option = option
    if best_score >= 70:
        return best_option
    return None


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
            page.locator(f'[value="{_attribute_escape(target)}"]'),
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


async def select_target(page, target: str, value: str, options: list[str] | None = None) -> None:
    locator = await resolve_locator(page, target)
    text_value = str(value)
    if options:
        text_value = _best_option_match(text_value, options) or text_value
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
        await select_target(page, target, coerced_value, field.options)
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

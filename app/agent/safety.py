from __future__ import annotations

from app.schemas import ExtractedField, PageState


SENSITIVE_KEYWORDS = {
    "gender",
    "race",
    "ethnicity",
    "disability",
    "veteran",
    "pronoun",
    "sexual orientation",
    "date of birth",
    "dob",
    "age",
}

EXPLICIT_PROFILE_PREFIXES = (
    "application_preferences.",
    "eeo.",
)

SAFE_KEYWORDS = {
    "first name",
    "last name",
    "full name",
    "email",
    "phone",
    "phone number",
    "location",
    "located",
    "country",
    "city",
    "state",
    "linkedin",
    "linkedin profile",
    "github",
    "portfolio",
    "website",
    "resume",
    "resume/cv",
    "authorized to work",
    "sponsorship",
    "salary expectation",
    "desired salary",
    "start date",
}

SUBMIT_KEYWORDS = {"submit", "send application", "finish application", "review and submit"}


def normalize_text(value: str | None) -> str:
    return (value or "").strip().lower()


def is_sensitive_label(label: str | None) -> bool:
    lowered = normalize_text(label)
    return any(keyword in lowered for keyword in SENSITIVE_KEYWORDS)


def is_sensitive_field(field: ExtractedField) -> bool:
    candidates = [
        field.label,
        field.name,
        field.placeholder,
        field.selector,
    ]
    return any(is_sensitive_label(candidate) for candidate in candidates)


def is_explicit_profile_path(path: str | None) -> bool:
    lowered = normalize_text(path)
    return any(lowered.startswith(prefix) for prefix in EXPLICIT_PROFILE_PREFIXES)


def is_safe_text(label: str | None) -> bool:
    lowered = normalize_text(label)
    return bool(lowered) and any(keyword in lowered for keyword in SAFE_KEYWORDS) and not is_sensitive_label(lowered)


def is_safe_field(field: ExtractedField) -> bool:
    candidates = [
        field.label,
        field.name,
        field.placeholder,
        field.selector,
    ]
    return any(is_safe_text(candidate) for candidate in candidates)


def should_stop_for_review(page_state: PageState) -> bool:
    for element in page_state.elements:
        if element.tag_name == "button" and element.text:
            lowered = element.text.lower()
            if any(keyword in lowered for keyword in SUBMIT_KEYWORDS):
                return True
    return False

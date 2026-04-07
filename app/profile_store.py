from __future__ import annotations

import re
from typing import Any

from rapidfuzz import fuzz


FIELD_MAP = {
    "full name": "identity.full_name",
    "first name": "identity.first_name",
    "last name": "identity.last_name",
    "email": "identity.email",
    "phone": "identity.phone",
    "phone number": "identity.phone",
    "country": "identity.country",
    "location": "identity.location",
    "where are you located": "identity.location",
    "current location": "identity.location",
    "linkedin": "identity.linkedin",
    "linkedin profile": "identity.linkedin",
    "github": "identity.github",
    "portfolio": "identity.portfolio",
    "website": "identity.portfolio",
    "authorized to work in the us": "work_auth.authorized_us",
    "authorized to work": "work_auth.authorized_us",
    "will you now or in the future require sponsorship": "work_auth.require_sponsorship",
    "require sponsorship": "work_auth.require_sponsorship",
    "sponsorship": "work_auth.require_sponsorship",
    "salary expectation": "defaults.salary_expectation",
    "desired salary": "defaults.salary_expectation",
    "start date": "defaults.start_date",
    "resume": "documents.resume_pdf",
    "resume/cv": "documents.resume_pdf",
    "current employee": "application_preferences.current_employee",
    "currently employed by this company": "application_preferences.current_employee",
    "already employed by this company": "application_preferences.current_employee",
    "already employed to this company": "application_preferences.current_employee",
    "gender": "eeo.gender",
    "sex": "eeo.gender",
    "hispanic ethnicity": "eeo.hispanic_latino",
    "hispanic or latino": "eeo.hispanic_latino",
    "hispanic latino": "eeo.hispanic_latino",
    "ethnicity": "eeo.ethnicity",
    "race": "eeo.ethnicity",
    "race ethnicity": "eeo.ethnicity",
    "veteran status": "eeo.veteran_status",
    "disability status": "eeo.disability_status",
    "disability": "eeo.disability_status",
}


def normalize_label(label: str) -> str:
    label = label.lower()
    label = re.sub(r"[^a-z0-9\s]", " ", label)
    label = re.sub(r"\s+", " ", label).strip()
    return label


def _get_nested(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _split_name(full_name: str) -> tuple[str | None, str | None]:
    pieces = [piece for piece in full_name.split() if piece]
    if not pieces:
        return None, None
    if len(pieces) == 1:
        return pieces[0], None
    return pieces[0], " ".join(pieces[1:])


def _derive_country(profile_data: dict[str, Any]) -> str | None:
    explicit_country = _get_nested(profile_data, "identity.country")
    if isinstance(explicit_country, str) and explicit_country.strip():
        return explicit_country.strip()

    location = _get_nested(profile_data, "identity.location")
    if not isinstance(location, str):
        return None
    parts = [part.strip() for part in location.split(",") if part.strip()]
    if not parts:
        return None
    return parts[-1]


def _rule_based_profile_path(normalized: str) -> str | None:
    if (
        any(token in normalized for token in {"current employee", "currently employed", "already employed"})
        and any(token in normalized for token in {"company", "employer", "organization", "here"})
    ):
        return "application_preferences.current_employee"
    if "gender" in normalized or normalized == "sex":
        return "eeo.gender"
    if "hispanic" in normalized or "latino" in normalized:
        return "eeo.hispanic_latino"
    if "veteran" in normalized:
        return "eeo.veteran_status"
    if "disability" in normalized or "disabled" in normalized:
        return "eeo.disability_status"
    if "ethnicity" in normalized or "race" in normalized:
        return "eeo.ethnicity"
    return None


def lookup_profile_value(label: str, profile_data: dict[str, Any], min_score: int = 88) -> tuple[str | None, Any]:
    normalized = normalize_label(label)
    if normalized in FIELD_MAP:
        path = FIELD_MAP[normalized]
        value = _get_nested(profile_data, path)
        if value is not None:
            return path, value

    rule_based_path = _rule_based_profile_path(normalized)
    if rule_based_path:
        value = _get_nested(profile_data, rule_based_path)
        if value is not None:
            return rule_based_path, value

    if normalized == "country":
        derived_country = _derive_country(profile_data)
        if derived_country:
            return "identity.country", derived_country

    if normalized in {"first name", "last name"}:
        full_name = _get_nested(profile_data, "identity.full_name")
        if isinstance(full_name, str):
            first_name, last_name = _split_name(full_name)
            if normalized == "first name" and first_name:
                return "identity.first_name", first_name
            if normalized == "last name" and last_name:
                return "identity.last_name", last_name

    best: tuple[int, str | None] = (0, None)
    for key, path in FIELD_MAP.items():
        score = fuzz.token_set_ratio(normalized, key)
        if score > best[0]:
            best = (score, path)

    if best[1] and best[0] >= min_score:
        value = _get_nested(profile_data, best[1])
        if value is not None:
            return best[1], value

    return None, None

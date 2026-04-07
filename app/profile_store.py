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
    "location": "identity.location",
    "linkedin": "identity.linkedin",
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


def lookup_profile_value(label: str, profile_data: dict[str, Any], min_score: int = 88) -> tuple[str | None, Any]:
    normalized = normalize_label(label)
    if normalized in FIELD_MAP:
        path = FIELD_MAP[normalized]
        value = _get_nested(profile_data, path)
        if value is not None:
            return path, value

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

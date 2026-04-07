from __future__ import annotations

import re
from typing import Iterable

from rapidfuzz import fuzz

from app.models import AnswerEntry


def normalize_prompt(prompt: str) -> str:
    prompt = prompt.lower()
    prompt = re.sub(r"[^a-z0-9\s]", " ", prompt)
    prompt = re.sub(r"\s+", " ", prompt).strip()
    return prompt


def best_answer_match(prompt: str, answers: Iterable[AnswerEntry], min_score: int = 85) -> AnswerEntry | None:
    normalized = normalize_prompt(prompt)
    best: tuple[int, AnswerEntry | None] = (0, None)
    for entry in answers:
        score = fuzz.token_set_ratio(normalized, entry.normalized_prompt)
        if score > best[0]:
            best = (score, entry)
    if best[0] >= min_score:
        return best[1]
    return None

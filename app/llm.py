from __future__ import annotations

import json

import httpx

from app.config import get_settings


class LLMError(RuntimeError):
    pass


def _extract_json(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:].strip()
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1:
        raise LLMError("Planner response did not contain a JSON object.")
    return json.loads(content[start : end + 1])


async def plan_next_action(prompt: str) -> dict:
    settings = get_settings()
    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": settings.planner_temperature,
    }
    async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
        response = await client.post(f"{settings.ollama_base_url}/v1/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise LLMError("Unexpected planner response shape.") from exc
    return _extract_json(content)

from __future__ import annotations

from app.llm import plan_next_action
from app.schemas import PageState, PlannerAction


def _elements_summary(page_state: PageState) -> str:
    rows = []
    for element in page_state.elements[:60]:
        rows.append(
            {
                "label": element.label,
                "selector": element.selector,
                "tag": element.tag_name,
                "type": element.input_type,
                "text": element.text,
                "options": element.options[:8],
            }
        )
    return str(rows)


def build_planner_prompt(page_state: PageState) -> str:
    return f"""
You are controlling a job application browser agent.

Rules:
- Output valid JSON only.
- Prefer visible labels and semantic targets.
- Never submit an application.
- If the page contains a final submit/review action, return action="done".
- If uncertain, return action="fail".

Page URL: {page_state.url}
Page title: {page_state.title}
Visible text summary:
{page_state.visible_text[:4000]}

Known interactive elements:
{_elements_summary(page_state)}

Goal:
Click apply, navigate application flow, and fill safe fields from profile.

Output schema:
{{
  "thought": "short reason",
  "action": "click|type|select|extract|done|fail",
  "target": "selector or visible label",
  "value": "optional text",
  "confidence": 0.0
}}
""".strip()


async def decide_next_action(page_state: PageState) -> PlannerAction:
    raw_action = await plan_next_action(build_planner_prompt(page_state))
    return PlannerAction.model_validate(raw_action)

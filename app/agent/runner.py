from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

from app.agent.actions import click_target, select_target, type_target
from app.agent.classifiers import detect_platform
from app.agent.extractor import extract_page_state
from app.agent.planner import decide_next_action
from app.agent.safety import should_stop_for_review
from app.config import get_settings
from app.db import session_scope
from app.models import Job, Profile, Run
from app.resume_customizer import ResumeCustomizationError, create_resume_variant, hydrate_profile_resume
from app.schemas import ResumeCustomizeRequest
from app.site_adapters import get_adapter


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _artifact_path(root: Path, run_id: str, suffix: str) -> Path:
    timestamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    return root / f"{run_id}-{timestamp}-{suffix}"


async def _save_snapshot(page, run_id: str) -> dict:
    settings = get_settings()
    screenshot_path = _artifact_path(settings.screenshots_path, run_id, "page.png")
    html_path = _artifact_path(settings.html_path, run_id, "page.html")
    await page.screenshot(path=str(screenshot_path), full_page=True)
    html_path.write_text(await page.content(), encoding="utf-8")
    return {
        "latest_screenshot": str(screenshot_path),
        "latest_html": str(html_path),
    }


async def _planner_navigate(page, decisions: list[dict]) -> None:
    settings = get_settings()
    for _ in range(settings.max_agent_steps):
        page_state = await extract_page_state(page)
        if should_stop_for_review(page_state):
            decisions.append(
                {
                    "action": "done",
                    "target": "review gate",
                    "source": "planner",
                    "note": "Detected submit/review control and stopped.",
                }
            )
            return

        action = await decide_next_action(page_state)
        decisions.append({**action.model_dump(), "source": "planner"})

        if action.action == "click":
            await click_target(page, action.target)
        elif action.action == "type" and action.value is not None:
            await type_target(page, action.target, action.value)
        elif action.action == "select" and action.value is not None:
            await select_target(page, action.target, action.value)
        elif action.action in {"extract", "done"}:
            return
        else:
            raise RuntimeError(f"Planner stopped with action: {action.model_dump()}")

        await page.wait_for_load_state("domcontentloaded")


async def execute_run(run_id: str) -> None:
    settings = get_settings()

    with session_scope() as session:
        run = session.get(Run, run_id)
        if run is None:
            raise ValueError(f"Run not found: {run_id}")
        job = session.get(Job, run.job_id)
        profile = session.get(Profile, run.profile_id)
        if job is None or profile is None:
            raise ValueError("Run is missing associated job or profile.")
        run.status = "running"
        run.started_at = utc_now()
        session.flush()
        job_url = job.url
        company = job.company
        job_title = job.title
        job_description = job.description
        profile_id = profile.id
        profile_data = hydrate_profile_resume(
            dict(profile.data or {}),
            resume_path=profile.resume_path,
        )
        answer_entries = list(profile.answers)

    trace_path = _artifact_path(settings.traces_path, run_id, "trace.zip")
    decisions: list[dict] = []
    artifacts: dict = {}
    result: dict = {}
    extracted_fields: list[dict] = []

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=settings.headless,
                slow_mo=settings.slow_mo_ms,
            )
            context = await browser.new_context()
            context.set_default_timeout(settings.navigation_timeout_ms)
            await context.tracing.start(screenshots=True, snapshots=True, sources=True)
            page = await context.new_page()
            await page.goto(job_url, wait_until="domcontentloaded")

            page_state = await extract_page_state(page)
            platform = detect_platform(page_state)
            adapter = get_adapter(platform)
            profile_data_for_run = deepcopy(profile_data)

            try:
                variant = await create_resume_variant(
                    profile_id=profile_id,
                    profile_data=profile_data_for_run,
                    job_request=ResumeCustomizeRequest(
                        job_url=job_url,
                        company=company,
                        job_title=job_title or page_state.title,
                        job_description=job_description or page_state.visible_text[:6000],
                    ),
                )
                documents = dict(profile_data_for_run.get("documents", {}))
                documents["resume_pdf"] = variant.pdf_path
                documents["tailored_resume_markdown_path"] = variant.markdown_path
                profile_data_for_run["documents"] = documents
                artifacts["tailored_resume"] = variant.model_dump(mode="json")
                decisions.append(
                    {
                        "action": "generate",
                        "target": "resume",
                        "source": "resume_customizer",
                        "note": f"Generated resume variant at {variant.pdf_path}",
                    }
                )
            except ResumeCustomizationError as exc:
                decisions.append(
                    {
                        "action": "skip",
                        "target": "resume",
                        "source": "resume_customizer",
                        "note": f"Resume customization skipped: {exc}",
                    }
                )
            except Exception as exc:
                decisions.append(
                    {
                        "action": "skip",
                        "target": "resume",
                        "source": "resume_customizer",
                        "note": f"Tailored resume generation failed, using base resume: {exc}",
                    }
                )

            with session_scope() as session:
                run = session.get(Run, run_id)
                job = session.get(Job, run.job_id)
                run.platform = platform
                job.platform = platform
                job.status = "running"
                if not job.title:
                    job.title = page_state.title
                if not job.description:
                    job.description = page_state.visible_text[:8000]

            started = await adapter.start_application(page)
            decisions.append(
                {
                    "action": "click" if started else "fallback",
                    "target": "apply",
                    "source": adapter.name,
                    "note": "Deterministic start_application attempt.",
                }
            )

            if not started:
                await _planner_navigate(page, decisions)

            fields, filled, skipped = await adapter.autofill_fields(page, profile_data_for_run, answer_entries)
            decisions.extend(filled)
            decisions.extend(skipped)
            extracted_fields = [field.model_dump() for field in fields]

            artifacts.update(await _save_snapshot(page, run_id))
            await context.tracing.stop(path=str(trace_path))
            artifacts["trace"] = str(trace_path)

            final_page_state = await extract_page_state(page)
            review_required = settings.require_human_approval or should_stop_for_review(final_page_state)
            result = {
                "company": company,
                "final_url": final_page_state.url,
                "page_title": final_page_state.title,
                "status": "review_required" if review_required else "completed",
            }

            with session_scope() as session:
                run = session.get(Run, run_id)
                job = session.get(Job, run.job_id)
                run.status = "review" if review_required else "completed"
                run.extracted_fields = extracted_fields
                run.decisions = decisions
                run.artifacts = artifacts
                run.pending_review = {
                    "requires_human_approval": review_required,
                    "final_url": final_page_state.url,
                    "fields": extracted_fields,
                    "tailored_resume": artifacts.get("tailored_resume"),
                }
                run.result = result
                run.finished_at = utc_now()
                job.status = run.status

            await browser.close()
    except Exception as exc:
        with session_scope() as session:
            run = session.get(Run, run_id)
            job = session.get(Job, run.job_id) if run else None
            if run:
                run.status = "failed"
                run.decisions = decisions
                run.artifacts = artifacts
                run.extracted_fields = extracted_fields
                run.result = result
                run.error_message = str(exc)
                run.finished_at = utc_now()
            if job:
                job.status = "failed"
        raise

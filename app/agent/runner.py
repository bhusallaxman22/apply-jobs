from __future__ import annotations

import asyncio
import logging
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

from app.agent.actions import click_target, select_target, type_target
from app.agent.classifiers import detect_platform
from app.agent.extractor import extract_page_state
from app.agent.live_sessions import (
    clear_live_run,
    register_live_run,
    reset_live_run_resume,
)
from app.agent.planner import decide_next_action
from app.agent.safety import SUBMIT_KEYWORDS, normalize_text, should_stop_for_review
from app.config import get_settings
from app.db import session_scope
from app.models import Job, Profile, Run
from app.resume_customizer import ResumeCustomizationError, create_resume_variant, hydrate_profile_resume
from app.schemas import ResumeCustomizeRequest
from app.site_adapters import get_adapter

logger = logging.getLogger(__name__)

CHECKPOINT_INTERVAL_SECONDS = 10.0
SUBMIT_RUN_TIMEOUT_SECONDS = 300.0
MAX_PROGRESS_SCREENSHOTS = 120
CAPTCHA_WAIT_POLL_SECONDS = 5.0
SUBMISSION_SUCCESS_TEXT = (
    "thank you for applying",
    "application submitted",
    "application received",
    "we received your application",
    "we've received your application",
    "successfully submitted",
)
CAPTCHA_TEXT_HINTS = (
    "captcha",
    "verify you are human",
    "verification required",
    "security check",
    "not a robot",
    "recaptcha",
    "hcaptcha",
    "turnstile",
    "press and hold",
    "unusual traffic",
)
CAPTCHA_SELECTOR_CANDIDATES = (
    'iframe[src*="recaptcha"]',
    'iframe[src*="hcaptcha"]',
    'iframe[src*="turnstile"]',
    'iframe[src*="challenges.cloudflare.com"]',
    ".g-recaptcha",
    ".h-captcha",
    ".cf-turnstile",
    '[name="g-recaptcha-response"]',
    '[name="h-captcha-response"]',
    '[name="cf-turnstile-response"]',
    '[data-sitekey]',
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _artifact_path(root: Path, run_id: str, suffix: str) -> Path:
    timestamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    return root / f"{run_id}-{timestamp}-{suffix}"


def _stamp_decision(entry: dict) -> dict:
    stamped = dict(entry)
    stamped.setdefault("logged_at", utc_now().isoformat())
    return stamped


def _append_decision(decisions: list[dict], entry: dict) -> None:
    decisions.append(_stamp_decision(entry))


def _extend_decisions(decisions: list[dict], entries: list[dict]) -> None:
    decisions.extend(_stamp_decision(entry) for entry in entries)


async def _save_snapshot(page, run_id: str, *, prefix: str = "latest", suffix: str = "page") -> dict:
    settings = get_settings()
    screenshot_path = _artifact_path(settings.screenshots_path, run_id, f"{suffix}.png")
    html_path = _artifact_path(settings.html_path, run_id, f"{suffix}.html")
    await page.screenshot(path=str(screenshot_path), full_page=True)
    html_path.write_text(await page.content(), encoding="utf-8")
    return {
        f"{prefix}_screenshot": str(screenshot_path),
        f"{prefix}_html": str(html_path),
    }


async def _persist_run_progress(
    *,
    run_id: str,
    status: str,
    decisions: list[dict],
    artifacts: dict,
    extracted_fields: list[dict],
    result: dict,
    error_message: str | None = None,
) -> None:
    with session_scope() as session:
        run = session.get(Run, run_id)
        if run is None:
            return
        job = session.get(Job, run.job_id)
        run.status = status
        run.decisions = deepcopy(decisions)
        run.artifacts = deepcopy(artifacts)
        run.extracted_fields = deepcopy(extracted_fields)
        run.result = deepcopy(result)
        if error_message is not None:
            run.error_message = error_message
        if job is not None:
            job.status = status


async def _checkpoint_progress(
    *,
    run_id: str,
    page,
    status: str,
    decisions: list[dict],
    artifacts: dict,
    extracted_fields: list[dict],
    result: dict,
    checkpoint_state: dict,
    reason: str,
    force: bool = False,
) -> dict | None:
    now = time.monotonic()
    last_monotonic = checkpoint_state.get("last_monotonic", 0.0)
    if not force and now - last_monotonic < CHECKPOINT_INTERVAL_SECONDS:
        return None

    checkpoint_index = int(checkpoint_state.get("count", 0)) + 1
    snapshot = await _save_snapshot(
        page,
        run_id,
        prefix="latest",
        suffix=f"checkpoint-{checkpoint_index:03d}",
    )
    page_state = await extract_page_state(page)
    captured_at = utc_now().isoformat()
    entry = {
        "path": snapshot["latest_screenshot"],
        "html_path": snapshot["latest_html"],
        "captured_at": captured_at,
        "url": page_state.url,
        "title": page_state.title,
        "reason": reason,
        "index": checkpoint_index,
    }
    history = list(artifacts.get("progress_screenshots") or [])
    history.append(entry)
    artifacts["progress_screenshots"] = history[-MAX_PROGRESS_SCREENSHOTS:]
    artifacts["latest_screenshot"] = snapshot["latest_screenshot"]
    artifacts["latest_html"] = snapshot["latest_html"]

    checkpoint_state["last_monotonic"] = now
    checkpoint_state["count"] = checkpoint_index
    _append_decision(
        decisions,
        {
            "action": "observe",
            "target": page_state.url,
            "source": "checkpoint",
            "note": reason,
        },
    )
    result.update(
        {
            "current_url": page_state.url,
            "current_page_title": page_state.title,
            "last_checkpoint_at": captured_at,
        }
    )
    await _persist_run_progress(
        run_id=run_id,
        status=status,
        decisions=decisions,
        artifacts=artifacts,
        extracted_fields=extracted_fields,
        result=result,
    )
    return page_state


async def _planner_navigate(page, decisions: list[dict], progress_hook=None) -> None:
    settings = get_settings()
    for _ in range(settings.max_agent_steps):
        page_state = await extract_page_state(page)
        if should_stop_for_review(page_state):
            _append_decision(
                decisions,
                {
                    "action": "done",
                    "target": "review gate",
                    "source": "planner",
                    "note": "Detected submit/review control and stopped.",
                }
            )
            return

        action = await decide_next_action(page_state)
        _append_decision(decisions, {**action.model_dump(), "source": "planner"})

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
        if progress_hook is not None:
            await progress_hook(f"Planner executed {action.action} on {action.target}.")


async def _wait_for_page_settle(page) -> None:
    settings = get_settings()
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=min(settings.navigation_timeout_ms, 5_000))
    except Exception:
        pass
    try:
        await page.wait_for_load_state("networkidle", timeout=3_000)
    except Exception:
        pass
    await page.wait_for_timeout(750)


async def _save_browser_state(context, run_id: str) -> str:
    settings = get_settings()
    state_path = _artifact_path(settings.browser_states_path, run_id, "storage-state.json")
    await context.storage_state(path=str(state_path))
    return str(state_path)


async def _finalize_captcha_pause(
    *,
    context,
    trace_path: Path,
    trace_key: str,
    run_id: str,
    decisions: list[dict],
    artifacts: dict,
    extracted_fields: list[dict],
    result: dict,
) -> None:
    await context.tracing.stop(path=str(trace_path))
    artifacts[trace_key] = str(trace_path)
    await _persist_run_progress(
        run_id=run_id,
        status="captcha_required",
        decisions=decisions,
        artifacts=artifacts,
        extracted_fields=extracted_fields,
        result=result,
    )


def _manual_browser_url() -> str | None:
    settings = get_settings()
    if not settings.browser_desktop_enabled:
        return None
    if settings.browser_desktop_public_url:
        return settings.browser_desktop_public_url
    return None


def _manual_browser_note() -> str:
    settings = get_settings()
    if not settings.browser_desktop_enabled:
        return "Live browser access is disabled. Enable BROWSER_DESKTOP_ENABLED and set BROWSER_DESKTOP_PUBLIC_URL to solve CAPTCHA in-session."
    if settings.browser_desktop_public_url:
        return "Open the live browser, solve the challenge, then press Resume after CAPTCHA."
    return (
        "Live browser access is enabled but no public URL is configured. "
        "Set BROWSER_DESKTOP_PUBLIC_URL so the dashboard can open the noVNC session directly."
    )


async def _detect_captcha(page, page_state=None) -> dict | None:
    page_state = page_state or await extract_page_state(page)
    visible_text = normalize_text(page_state.visible_text)
    title = normalize_text(page_state.title)
    url = normalize_text(page_state.url)
    matched_signals: list[str] = []

    for token in CAPTCHA_TEXT_HINTS:
        if token in visible_text or token in title or token in url:
            matched_signals.append(token)

    matched_selectors: list[str] = []
    for selector in CAPTCHA_SELECTOR_CANDIDATES:
        try:
            if await page.locator(selector).count():
                matched_selectors.append(selector)
        except Exception:
            continue

    if not matched_signals and not matched_selectors:
        return None

    reason_parts: list[str] = []
    if matched_signals:
        reason_parts.append(f"text markers: {', '.join(sorted(set(matched_signals)))}")
    if matched_selectors:
        reason_parts.append(f"DOM markers: {', '.join(matched_selectors)}")

    return {
        "reason": "CAPTCHA challenge detected via " + "; ".join(reason_parts),
        "signals": sorted(set(matched_signals)),
        "selectors": matched_selectors,
        "page_state": page_state,
    }


def _browser_headless(settings) -> bool:
    return settings.headless and not settings.browser_desktop_enabled


async def _store_captcha_required_state(
    *,
    run_id: str,
    status_after_resume: str,
    page,
    context,
    decisions: list[dict],
    artifacts: dict,
    extracted_fields: list[dict],
    result: dict,
    captcha_data: dict,
    note: str,
) -> dict:
    page_state = captcha_data["page_state"]
    snapshot = await _save_snapshot(page, run_id, prefix="latest", suffix="captcha")
    artifacts.update(snapshot)
    artifacts["captcha_screenshot"] = snapshot["latest_screenshot"]
    artifacts["captcha_html"] = snapshot["latest_html"]
    try:
        browser_state_path = await _save_browser_state(context, run_id)
        artifacts["browser_state"] = browser_state_path
    except Exception as exc:
        logger.warning("Run %s could not save browser state during CAPTCHA pause: %s", run_id, exc)

    _append_decision(
        decisions,
        {
            "action": "pause",
            "target": page_state.url,
            "source": "captcha",
            "note": note,
        },
    )
    result.update(
        {
            "status": "captcha_required",
            "current_url": page_state.url,
            "page_title": page_state.title,
            "captcha_required_at": utc_now().isoformat(),
        }
    )
    manual_browser_url = _manual_browser_url()
    manual_note = _manual_browser_note()

    with session_scope() as session:
        run = session.get(Run, run_id)
        if run is None:
            return {
                "manual_browser_url": manual_browser_url,
                "manual_note": manual_note,
                "page_state": page_state,
            }
        job = session.get(Job, run.job_id)
        run.status = "captcha_required"
        run.decisions = deepcopy(decisions)
        run.artifacts = deepcopy(artifacts)
        run.extracted_fields = deepcopy(extracted_fields)
        run.result = deepcopy(result)
        run.error_message = None
        run.pending_review = {
            **(run.pending_review or {}),
            "captcha_detected": True,
            "captcha_reason": captcha_data["reason"],
            "captcha_signals": captcha_data["signals"],
            "captcha_selectors": captcha_data["selectors"],
            "final_url": page_state.url,
            "fields": deepcopy(extracted_fields),
            "browser_state": artifacts.get("browser_state"),
            "manual_browser_url": manual_browser_url,
            "manual_browser_note": manual_note,
            "resume_status": status_after_resume,
        }
        if job is not None:
            job.status = run.status

    return {
        "manual_browser_url": manual_browser_url,
        "manual_note": manual_note,
        "page_state": page_state,
    }


async def _wait_for_manual_captcha_resolution(
    *,
    run_id: str,
    status_after_resume: str,
    page,
    context,
    decisions: list[dict],
    artifacts: dict,
    extracted_fields: list[dict],
    result: dict,
    checkpoint_state: dict,
    captcha_data: dict,
) -> bool:
    settings = get_settings()
    note = captcha_data["reason"]
    captcha_state = await _store_captcha_required_state(
        run_id=run_id,
        status_after_resume=status_after_resume,
        page=page,
        context=context,
        decisions=decisions,
        artifacts=artifacts,
        extracted_fields=extracted_fields,
        result=result,
        captcha_data=captcha_data,
        note=note,
    )
    async def captcha_progress_hook(reason: str, *, force: bool = False) -> dict | None:
        return await _checkpoint_progress(
            run_id=run_id,
            page=page,
            status="captcha_required",
            decisions=decisions,
            artifacts=artifacts,
            extracted_fields=extracted_fields,
            result=result,
            checkpoint_state=checkpoint_state,
            reason=reason,
            force=force,
        )

    await captcha_progress_hook("CAPTCHA detected and run paused for manual solve.", force=True)

    if not settings.browser_desktop_enabled:
        logger.warning("Run %s entered captcha_required, but live browser access is disabled.", run_id)
        return False

    live_run = register_live_run(run_id, status_after_resume)
    logger.warning("Run %s paused for manual CAPTCHA solve.", run_id)

    deadline = time.monotonic() + max(settings.captcha_wait_timeout_seconds, 1)
    try:
        while True:
            if live_run.cancel_event.is_set():
                logger.info("Run %s manual CAPTCHA flow canceled.", run_id)
                return False

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timeout_note = (
                    f"Manual CAPTCHA solve timed out after {int(settings.captcha_wait_timeout_seconds)} seconds. "
                    "Reopen the run and retry when ready."
                )
                captcha_data = await _detect_captcha(page) or captcha_data
                await _store_captcha_required_state(
                    run_id=run_id,
                    status_after_resume=status_after_resume,
                    page=page,
                    context=context,
                    decisions=decisions,
                    artifacts=artifacts,
                    extracted_fields=extracted_fields,
                    result=result,
                    captcha_data=captcha_data,
                    note=timeout_note,
                )
                logger.warning("Run %s timed out while waiting for manual CAPTCHA solve.", run_id)
                return False

            try:
                await asyncio.wait_for(
                    live_run.resume_event.wait(),
                    timeout=min(CAPTCHA_WAIT_POLL_SECONDS, remaining),
                )
            except TimeoutError:
                await captcha_progress_hook("Waiting for manual CAPTCHA solve in the live browser.")
                continue

            reset_live_run_resume(run_id)
            await _wait_for_page_settle(page)
            current_captcha = await _detect_captcha(page)
            if current_captcha is not None:
                retry_note = (
                    current_captcha["reason"]
                    + ". Resume was requested, but the challenge still appears to be present."
                )
                await _store_captcha_required_state(
                    run_id=run_id,
                    status_after_resume=status_after_resume,
                    page=page,
                    context=context,
                    decisions=decisions,
                    artifacts=artifacts,
                    extracted_fields=extracted_fields,
                    result=result,
                    captcha_data=current_captcha,
                    note=retry_note,
                )
                await captcha_progress_hook("CAPTCHA still detected after manual resume request.", force=True)
                continue

            _append_decision(
                decisions,
                {
                    "action": "resume",
                    "target": captcha_state["page_state"].url,
                    "source": "captcha",
                    "note": "Manual CAPTCHA solve cleared. Resuming automation.",
                },
            )
            result.update(
                {
                    "status": status_after_resume,
                    "current_url": page.url,
                    "page_title": await page.title(),
                }
            )
            with session_scope() as session:
                run = session.get(Run, run_id)
                job = session.get(Job, run.job_id) if run else None
                if run is not None:
                    run.status = status_after_resume
                    run.decisions = deepcopy(decisions)
                    run.artifacts = deepcopy(artifacts)
                    run.extracted_fields = deepcopy(extracted_fields)
                    run.result = deepcopy(result)
                    run.error_message = None
                    run.pending_review = {
                        **(run.pending_review or {}),
                        "captcha_detected": False,
                        "captcha_reason": None,
                        "manual_browser_url": _manual_browser_url(),
                        "manual_browser_note": _manual_browser_note(),
                    }
                if job is not None:
                    job.status = status_after_resume
            await _checkpoint_progress(
                run_id=run_id,
                page=page,
                status=status_after_resume,
                decisions=decisions,
                artifacts=artifacts,
                extracted_fields=extracted_fields,
                result=result,
                checkpoint_state=checkpoint_state,
                reason="Manual CAPTCHA solve acknowledged. Resuming automation.",
                force=True,
            )
            logger.info("Run %s resumed after manual CAPTCHA solve.", run_id)
            return True
    finally:
        clear_live_run(run_id)


def _candidate_submit_targets(page_state) -> list[str]:
    targets: list[str] = []
    seen: set[str] = set()

    for element in page_state.elements:
        candidates = [
            element.text,
            element.label,
            getattr(element, "value", None),
        ]
        if not any(
            candidate and any(keyword in normalize_text(candidate) for keyword in SUBMIT_KEYWORDS)
            for candidate in candidates
        ):
            continue

        target = element.selector or element.text or element.label or getattr(element, "value", None)
        if not target or target in seen:
            continue
        seen.add(target)
        targets.append(target)

    for keyword in SUBMIT_KEYWORDS:
        if keyword not in seen:
            targets.append(keyword)

    return targets


async def _click_submit(page, decisions: list[dict]) -> str:
    page_state = await extract_page_state(page)
    for target in _candidate_submit_targets(page_state):
        try:
            await click_target(page, target)
            _append_decision(
                decisions,
                {
                    "action": "click",
                    "target": target,
                    "source": "submitter",
                    "note": "Clicked final submit control after approval.",
                }
            )
            logger.info("Clicked submit target %r.", target)
            return target
        except Exception:
            continue
    raise RuntimeError("Could not find a clickable submit control on the approved page.")


def _submission_looks_complete(before_state, after_state) -> bool:
    visible_text = normalize_text(after_state.visible_text)
    title = normalize_text(after_state.title)
    if any(token in visible_text for token in SUBMISSION_SUCCESS_TEXT):
        return True
    if any(token in title for token in SUBMISSION_SUCCESS_TEXT):
        return True
    if after_state.url != before_state.url and not should_stop_for_review(after_state):
        return True
    return False


async def _progress_application_until_submit(
    page,
    adapter,
    profile_data: dict,
    answer_entries: list,
    decisions: list[dict],
    progress_hook=None,
) -> list[dict]:
    settings = get_settings()
    latest_fields: list[dict] = []

    for _ in range(settings.max_agent_steps):
        fields, filled, skipped = await adapter.autofill_fields(page, profile_data, answer_entries)
        _extend_decisions(decisions, filled)
        _extend_decisions(decisions, skipped)
        latest_fields = [field.model_dump() for field in fields]
        if progress_hook is not None:
            await progress_hook(f"Autofill inspected {len(fields)} fields.")

        page_state = await extract_page_state(page)
        if should_stop_for_review(page_state):
            return latest_fields

        action = await decide_next_action(page_state)
        _append_decision(decisions, {**action.model_dump(), "source": "planner"})

        if action.action == "click":
            await click_target(page, action.target)
        elif action.action == "type" and action.value is not None:
            await type_target(page, action.target, action.value)
        elif action.action == "select" and action.value is not None:
            await select_target(page, action.target, action.value)
        elif action.action in {"extract", "done"}:
            break
        else:
            raise RuntimeError(f"Planner stopped with action: {action.model_dump()}")

        await _wait_for_page_settle(page)
        if progress_hook is not None:
            await progress_hook(f"Planner advanced with {action.action} on {action.target}.")

    return latest_fields


def _attach_review_resume(profile_data: dict, run: Run) -> dict:
    updated = deepcopy(profile_data)
    tailored_resume = (
        (run.pending_review or {}).get("tailored_resume")
        or (run.artifacts or {}).get("tailored_resume")
        or {}
    )
    documents = dict(updated.get("documents", {}))
    pdf_path = tailored_resume.get("pdf_path")
    markdown_path = tailored_resume.get("markdown_path")
    if pdf_path and Path(pdf_path).is_file():
        documents["resume_pdf"] = pdf_path
    if markdown_path and Path(markdown_path).is_file():
        documents["tailored_resume_markdown_path"] = markdown_path
    if documents:
        updated["documents"] = documents
    return updated


async def submit_approved_run(run_id: str) -> None:
    settings = get_settings()

    with session_scope() as session:
        run = session.get(Run, run_id)
        if run is None:
            raise ValueError(f"Run not found: {run_id}")
        job = session.get(Job, run.job_id)
        profile = session.get(Profile, run.profile_id)
        if job is None or profile is None:
            raise ValueError("Run is missing associated job or profile.")

        answer_entries = list(profile.answers)
        profile_data = hydrate_profile_resume(
            dict(profile.data or {}),
            resume_path=profile.resume_path,
        )
        profile_data = _attach_review_resume(profile_data, run)
        review_url = ((run.pending_review or {}).get("final_url") or job.url)
        browser_state_path = ((run.pending_review or {}).get("browser_state") or (run.artifacts or {}).get("browser_state"))
        decisions = list(run.decisions or [])
        artifacts = dict(run.artifacts or {})
        result = dict(run.result or {})
        extracted_fields = list(run.extracted_fields or [])
        platform = run.platform or job.platform or "unknown"
        logger.info("Starting approved-submit flow for run %s on %s.", run_id, review_url)

    trace_path = _artifact_path(settings.traces_path, run_id, "submit-trace.zip")
    checkpoint_state = {"last_monotonic": 0.0, "count": len(artifacts.get("progress_screenshots") or [])}

    async def progress_hook(reason: str, *, force: bool = False) -> dict | None:
        return await _checkpoint_progress(
            run_id=run_id,
            page=page,
            status="submitting",
            decisions=decisions,
            artifacts=artifacts,
            extracted_fields=extracted_fields,
            result=result,
            checkpoint_state=checkpoint_state,
            reason=reason,
            force=force,
        )

    try:
        async with asyncio.timeout(SUBMIT_RUN_TIMEOUT_SECONDS):
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    headless=_browser_headless(settings),
                    slow_mo=settings.slow_mo_ms,
                )
                context_kwargs = {}
                if browser_state_path and Path(browser_state_path).is_file():
                    context_kwargs["storage_state"] = browser_state_path
                    logger.info("Run %s restored browser state from %s.", run_id, browser_state_path)
                context = await browser.new_context(**context_kwargs)
                context.set_default_timeout(settings.navigation_timeout_ms)
                await context.tracing.start(screenshots=True, snapshots=True, sources=True)
                page = await context.new_page()
                await page.goto(review_url, wait_until="domcontentloaded")
                await progress_hook("Opened approved run at the saved review URL.", force=True)
                captcha_data = await _detect_captcha(page)
                if captcha_data is not None:
                    should_resume = await _wait_for_manual_captcha_resolution(
                        run_id=run_id,
                        status_after_resume="submitting",
                        page=page,
                        context=context,
                        decisions=decisions,
                        artifacts=artifacts,
                        extracted_fields=extracted_fields,
                        result=result,
                        checkpoint_state=checkpoint_state,
                        captcha_data=captcha_data,
                    )
                    if not should_resume:
                        await _finalize_captcha_pause(
                            context=context,
                            trace_path=trace_path,
                            trace_key="submission_trace",
                            run_id=run_id,
                            decisions=decisions,
                            artifacts=artifacts,
                            extracted_fields=extracted_fields,
                            result=result,
                        )
                        await browser.close()
                        return

                adapter = get_adapter(platform)
                initial_state = await extract_page_state(page)
                if not should_stop_for_review(initial_state):
                    started = await adapter.start_application(page)
                    _append_decision(
                        decisions,
                        {
                            "action": "click" if started else "fallback",
                            "target": "apply",
                            "source": adapter.name,
                            "note": "Approved-submit flow attempted to reopen the application form.",
                        }
                    )
                    if started:
                        logger.info("Run %s reopened application flow with adapter %s.", run_id, adapter.name)
                        await _wait_for_page_settle(page)
                        captcha_data = await _detect_captcha(page)
                        if captcha_data is not None:
                            should_resume = await _wait_for_manual_captcha_resolution(
                                run_id=run_id,
                                status_after_resume="submitting",
                                page=page,
                                context=context,
                                decisions=decisions,
                                artifacts=artifacts,
                                extracted_fields=extracted_fields,
                                result=result,
                                checkpoint_state=checkpoint_state,
                                captcha_data=captcha_data,
                            )
                            if not should_resume:
                                await _finalize_captcha_pause(
                                    context=context,
                                    trace_path=trace_path,
                                    trace_key="submission_trace",
                                    run_id=run_id,
                                    decisions=decisions,
                                    artifacts=artifacts,
                                    extracted_fields=extracted_fields,
                                    result=result,
                                )
                                await browser.close()
                                return
                    await progress_hook("Tried to reopen the application form after approval.", force=True)

                extracted_fields = await _progress_application_until_submit(
                    page,
                    adapter,
                    profile_data,
                    answer_entries,
                    decisions,
                    progress_hook=progress_hook,
                )

                captcha_data = await _detect_captcha(page)
                if captcha_data is not None:
                    should_resume = await _wait_for_manual_captcha_resolution(
                        run_id=run_id,
                        status_after_resume="submitting",
                        page=page,
                        context=context,
                        decisions=decisions,
                        artifacts=artifacts,
                        extracted_fields=extracted_fields,
                        result=result,
                        checkpoint_state=checkpoint_state,
                        captcha_data=captcha_data,
                    )
                    if not should_resume:
                        await _finalize_captcha_pause(
                            context=context,
                            trace_path=trace_path,
                            trace_key="submission_trace",
                            run_id=run_id,
                            decisions=decisions,
                            artifacts=artifacts,
                            extracted_fields=extracted_fields,
                            result=result,
                        )
                        await browser.close()
                        return

                review_state = await extract_page_state(page)
                if not should_stop_for_review(review_state):
                    raise RuntimeError("Approved submit could not reach a final submit step.")

                await _click_submit(page, decisions)
                await _wait_for_page_settle(page)
                final_state = await extract_page_state(page)
                captcha_data = await _detect_captcha(page, final_state)
                if captcha_data is not None:
                    should_resume = await _wait_for_manual_captcha_resolution(
                        run_id=run_id,
                        status_after_resume="submitting",
                        page=page,
                        context=context,
                        decisions=decisions,
                        artifacts=artifacts,
                        extracted_fields=extracted_fields,
                        result=result,
                        checkpoint_state=checkpoint_state,
                        captcha_data=captcha_data,
                    )
                    if not should_resume:
                        await _finalize_captcha_pause(
                            context=context,
                            trace_path=trace_path,
                            trace_key="submission_trace",
                            run_id=run_id,
                            decisions=decisions,
                            artifacts=artifacts,
                            extracted_fields=extracted_fields,
                            result=result,
                        )
                        await browser.close()
                        return
                    final_state = await extract_page_state(page)
                await progress_hook("Clicked final submit control after approval.", force=True)

                submitted_artifacts = await _save_snapshot(page, run_id, prefix="submitted", suffix="submitted-page")
                artifacts.update(submitted_artifacts)
                artifacts["latest_screenshot"] = submitted_artifacts["submitted_screenshot"]
                artifacts["latest_html"] = submitted_artifacts["submitted_html"]
                await context.tracing.stop(path=str(trace_path))
                artifacts["submission_trace"] = str(trace_path)

                if not _submission_looks_complete(review_state, final_state):
                    raise RuntimeError("Submit was clicked, but the page did not show a clear submission confirmation.")

                result.update(
                    {
                        "status": "completed",
                        "final_url": final_state.url,
                        "page_title": final_state.title,
                        "submitted": True,
                        "submitted_at": utc_now().isoformat(),
                    }
                )

                with session_scope() as session:
                    run = session.get(Run, run_id)
                    job = session.get(Job, run.job_id)
                    run.status = "completed"
                    run.decisions = decisions
                    run.artifacts = artifacts
                    run.extracted_fields = extracted_fields
                    run.result = result
                    run.error_message = None
                    run.pending_review = {
                        **(run.pending_review or {}),
                        "approved": True,
                        "submission_error": None,
                        "submitted": True,
                        "final_url": final_state.url,
                        "fields": extracted_fields,
                    }
                    run.finished_at = utc_now()
                    job.status = run.status
                    logger.info("Run %s auto-submitted successfully.", run_id)

                await browser.close()
    except TimeoutError as exc:
        exc = RuntimeError(f"Approved submit timed out after {int(SUBMIT_RUN_TIMEOUT_SECONDS)} seconds.")
        result.update({"status": "review_required", "submitted": False})
        with session_scope() as session:
            run = session.get(Run, run_id)
            job = session.get(Job, run.job_id) if run else None
            if run:
                run.status = "review"
                run.decisions = decisions
                run.artifacts = artifacts
                run.extracted_fields = extracted_fields
                run.result = {
                    **result,
                    "status": "review_required",
                    "submitted": False,
                }
                run.error_message = str(exc)
                run.pending_review = {
                    **(run.pending_review or {}),
                    "approved": True,
                    "submission_error": str(exc),
                    "fields": extracted_fields or (run.pending_review or {}).get("fields", []),
                }
                run.finished_at = utc_now()
            if job:
                job.status = "review"
        logger.exception("Approved-submit flow timed out for run %s: %s", run_id, exc)
        raise exc
    except Exception as exc:
        result.update({"status": "review_required", "submitted": False})
        with session_scope() as session:
            run = session.get(Run, run_id)
            job = session.get(Job, run.job_id) if run else None
            if run:
                run.status = "review"
                run.decisions = decisions
                run.artifacts = artifacts
                run.extracted_fields = extracted_fields
                run.result = {
                    **result,
                    "status": "review_required",
                    "submitted": False,
                }
                run.error_message = str(exc)
                run.pending_review = {
                    **(run.pending_review or {}),
                    "approved": True,
                    "submission_error": str(exc),
                    "fields": extracted_fields or (run.pending_review or {}).get("fields", []),
                }
                run.finished_at = utc_now()
            if job:
                job.status = "review"
        logger.exception("Approved-submit flow failed for run %s: %s", run_id, exc)
        raise


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
        logger.info(
            "Starting run %s for profile %s on job %s (%s).",
            run.id,
            profile.id,
            job.id,
            job.url,
        )

    trace_path = _artifact_path(settings.traces_path, run_id, "trace.zip")
    decisions: list[dict] = []
    artifacts: dict = {}
    result: dict = {}
    extracted_fields: list[dict] = []
    checkpoint_state = {"last_monotonic": 0.0, "count": 0}

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=_browser_headless(settings),
                slow_mo=settings.slow_mo_ms,
            )
            context = await browser.new_context()
            context.set_default_timeout(settings.navigation_timeout_ms)
            await context.tracing.start(screenshots=True, snapshots=True, sources=True)
            page = await context.new_page()
            await page.goto(job_url, wait_until="domcontentloaded")

            async def progress_hook(reason: str, *, force: bool = False) -> dict | None:
                return await _checkpoint_progress(
                    run_id=run_id,
                    page=page,
                    status="running",
                    decisions=decisions,
                    artifacts=artifacts,
                    extracted_fields=extracted_fields,
                    result=result,
                    checkpoint_state=checkpoint_state,
                    reason=reason,
                    force=force,
                )

            await progress_hook("Opened the job page.", force=True)

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
                _append_decision(
                    decisions,
                    {
                        "action": "generate",
                        "target": "resume",
                        "source": "resume_customizer",
                        "note": f"Generated resume variant at {variant.pdf_path}",
                    }
                )
                logger.info("Run %s generated resume variant at %s.", run_id, variant.pdf_path)
            except ResumeCustomizationError as exc:
                _append_decision(
                    decisions,
                    {
                        "action": "skip",
                        "target": "resume",
                        "source": "resume_customizer",
                        "note": f"Resume customization skipped: {exc}",
                    }
                )
                logger.warning("Run %s skipped resume customization: %s", run_id, exc)
            except Exception as exc:
                _append_decision(
                    decisions,
                    {
                        "action": "skip",
                        "target": "resume",
                        "source": "resume_customizer",
                        "note": f"Tailored resume generation failed, using base resume: {exc}",
                    }
                )
                logger.exception("Run %s failed during resume generation; continuing with fallback/base resume.", run_id)

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
            _append_decision(
                decisions,
                {
                    "action": "click" if started else "fallback",
                    "target": "apply",
                    "source": adapter.name,
                    "note": "Deterministic start_application attempt.",
                }
            )
            logger.info(
                "Run %s adapter %s start_application returned %s.",
                run_id,
                adapter.name,
                started,
            )
            await progress_hook("Attempted to click the apply entrypoint.", force=True)
            captcha_data = await _detect_captcha(page)
            if captcha_data is not None:
                should_resume = await _wait_for_manual_captcha_resolution(
                    run_id=run_id,
                    status_after_resume="running",
                    page=page,
                    context=context,
                    decisions=decisions,
                    artifacts=artifacts,
                    extracted_fields=extracted_fields,
                    result=result,
                    checkpoint_state=checkpoint_state,
                    captcha_data=captcha_data,
                )
                if not should_resume:
                    await _finalize_captcha_pause(
                        context=context,
                        trace_path=trace_path,
                        trace_key="trace",
                        run_id=run_id,
                        decisions=decisions,
                        artifacts=artifacts,
                        extracted_fields=extracted_fields,
                        result=result,
                    )
                    await browser.close()
                    return

            if not started:
                await _planner_navigate(page, decisions, progress_hook=progress_hook)
                captcha_data = await _detect_captcha(page)
                if captcha_data is not None:
                    should_resume = await _wait_for_manual_captcha_resolution(
                        run_id=run_id,
                        status_after_resume="running",
                        page=page,
                        context=context,
                        decisions=decisions,
                        artifacts=artifacts,
                        extracted_fields=extracted_fields,
                        result=result,
                        checkpoint_state=checkpoint_state,
                        captcha_data=captcha_data,
                    )
                    if not should_resume:
                        await _finalize_captcha_pause(
                            context=context,
                            trace_path=trace_path,
                            trace_key="trace",
                            run_id=run_id,
                            decisions=decisions,
                            artifacts=artifacts,
                            extracted_fields=extracted_fields,
                            result=result,
                        )
                        await browser.close()
                        return

            fields, filled, skipped = await adapter.autofill_fields(page, profile_data_for_run, answer_entries)
            _extend_decisions(decisions, filled)
            _extend_decisions(decisions, skipped)
            extracted_fields = [field.model_dump() for field in fields]
            logger.info(
                "Run %s autofill completed with %d fields, %d filled actions, %d skipped actions.",
                run_id,
                len(fields),
                len(filled),
                len(skipped),
            )
            await progress_hook(f"Autofill completed with {len(fields)} extracted fields.", force=True)
            captcha_data = await _detect_captcha(page)
            if captcha_data is not None:
                should_resume = await _wait_for_manual_captcha_resolution(
                    run_id=run_id,
                    status_after_resume="running",
                    page=page,
                    context=context,
                    decisions=decisions,
                    artifacts=artifacts,
                    extracted_fields=extracted_fields,
                    result=result,
                    checkpoint_state=checkpoint_state,
                    captcha_data=captcha_data,
                )
                if not should_resume:
                    await _finalize_captcha_pause(
                        context=context,
                        trace_path=trace_path,
                        trace_key="trace",
                        run_id=run_id,
                        decisions=decisions,
                        artifacts=artifacts,
                        extracted_fields=extracted_fields,
                        result=result,
                    )
                    await browser.close()
                    return

            final_page_state = await extract_page_state(page)
            review_required = settings.require_human_approval or should_stop_for_review(final_page_state)
            artifacts.update(await _save_snapshot(page, run_id))
            if review_required:
                artifacts["review_screenshot"] = artifacts.get("latest_screenshot")
                artifacts["review_html"] = artifacts.get("latest_html")
                try:
                    browser_state_path = await _save_browser_state(context, run_id)
                    artifacts["browser_state"] = browser_state_path
                except Exception as exc:
                    logger.warning("Run %s could not save browser state for review: %s", run_id, exc)
            await context.tracing.stop(path=str(trace_path))
            artifacts["trace"] = str(trace_path)
            result = {
                "company": company,
                "final_url": final_page_state.url,
                "page_title": final_page_state.title,
                "status": "review_required" if review_required else "completed",
            }
            await _persist_run_progress(
                run_id=run_id,
                status="review" if review_required else "completed",
                decisions=decisions,
                artifacts=artifacts,
                extracted_fields=extracted_fields,
                result=result,
            )

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
                    "browser_state": artifacts.get("browser_state"),
                }
                run.result = result
                run.finished_at = utc_now()
                job.status = run.status
                logger.info(
                    "Run %s finished with status %s for job %s.",
                    run_id,
                    run.status,
                    job.id,
                )

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
        logger.exception("Run %s failed: %s", run_id, exc)
        raise

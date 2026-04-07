from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
import re
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Job, JobSource
from app.schemas import JobRead, JobSourceCreate, JobSourceRead, JobSourceSyncRead


class JobSourceError(RuntimeError):
    pass


PUBLIC_SOURCE_HEADERS = {
    "User-Agent": "apply-jobs/1.0 (+https://github.com/bhusallaxman22/apply-jobs)",
    "Accept": "application/json, text/plain;q=0.9, */*;q=0.8",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|li|h1|h2|h3|h4|section)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def normalize_platform(value: str) -> str:
    lowered = value.strip().lower()
    if "greenhouse" in lowered:
        return "greenhouse"
    if "lever" in lowered:
        return "lever"
    if "ashby" in lowered:
        return "ashby"
    if "recruitee" in lowered:
        return "recruitee"
    raise JobSourceError(f"Unsupported job source platform: {value}")


def detect_platform_from_url(source_url: str) -> str:
    hostname = urlparse(source_url).hostname or ""
    lowered = hostname.lower()
    if "greenhouse" in lowered:
        return "greenhouse"
    if "lever.co" in lowered:
        return "lever"
    if "ashbyhq.com" in lowered:
        return "ashby"
    if lowered.endswith(".recruitee.com") or lowered == "recruitee.com":
        return "recruitee"
    raise JobSourceError(f"Could not detect source platform from URL: {source_url}")


def extract_source_token(*, platform: str, source_url: str | None, source_token: str | None) -> str:
    if source_token:
        return source_token.strip().strip("/")
    if not source_url:
        raise JobSourceError("source_url is required when source_token is not provided.")

    parsed = urlparse(source_url)
    hostname = (parsed.hostname or "").lower()
    path_parts = [part for part in parsed.path.split("/") if part]
    if not path_parts:
        raise JobSourceError(f"Could not determine source token from URL: {source_url}")

    if platform == "greenhouse":
        if hostname == "boards-api.greenhouse.io" and len(path_parts) >= 3 and path_parts[:2] == ["v1", "boards"]:
            return path_parts[2]
        return path_parts[0]
    if platform == "lever":
        if hostname == "api.lever.co" and len(path_parts) >= 3 and path_parts[:2] == ["v0", "postings"]:
            return path_parts[2]
        return path_parts[0]
    if platform == "ashby":
        if hostname == "api.ashbyhq.com" and len(path_parts) >= 3 and path_parts[:2] == ["posting-api", "job-board"]:
            return path_parts[2]
        return path_parts[0]
    if platform == "recruitee":
        hostname_parts = [part for part in hostname.split(".") if part]
        if len(hostname_parts) >= 3 and hostname_parts[-2:] == ["recruitee", "com"]:
            return hostname_parts[0]
        raise JobSourceError(f"Could not determine Recruitee company token from URL: {source_url}")
    raise JobSourceError(f"Unsupported platform for token extraction: {platform}")


@dataclass
class ImportedJob:
    external_job_id: str
    url: str
    title: str
    company: str | None
    description: str
    location: str | None
    employment_type: str | None
    platform: str
    source_metadata: dict


def _public_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=get_settings().llm_timeout_seconds,
        headers=PUBLIC_SOURCE_HEADERS,
        follow_redirects=True,
    )


def humanize_code(value: str | None) -> str | None:
    if not value:
        return None
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    normalized = re.sub(r"[_-]+", " ", spaced)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.title() if normalized else None


async def fetch_greenhouse_jobs(source_token: str) -> tuple[str | None, list[ImportedJob]]:
    base_url = f"https://boards-api.greenhouse.io/v1/boards/{source_token}"
    async with _public_client() as client:
        board_response = await client.get(base_url)
        jobs_response = await client.get(f"{base_url}/jobs", params={"content": "true"})
    board_response.raise_for_status()
    jobs_response.raise_for_status()

    board_data = board_response.json()
    jobs_data = jobs_response.json()
    company_name = board_data.get("name") or source_token

    jobs: list[ImportedJob] = []
    for item in jobs_data.get("jobs", []):
        metadata = {
            "departments": item.get("departments", []),
            "offices": item.get("offices", []),
            "updated_at": item.get("updated_at"),
        }
        location = None
        if isinstance(item.get("location"), dict):
            location = item["location"].get("name")
        if not location and item.get("offices"):
            office_names = [office.get("name") for office in item["offices"] if office.get("name")]
            if office_names:
                location = ", ".join(office_names)

        jobs.append(
            ImportedJob(
                external_job_id=str(item["id"]),
                url=item.get("absolute_url") or item.get("url"),
                title=item.get("title") or "Untitled Job",
                company=company_name,
                description=strip_html(item.get("content")),
                location=location,
                employment_type=None,
                platform="greenhouse",
                source_metadata=metadata,
            )
        )
    return company_name, jobs


def _lever_description(item: dict) -> str:
    parts = [
        strip_html(item.get("descriptionPlain") or item.get("description")),
        strip_html(item.get("additionalPlain") or item.get("additional")),
    ]
    lists = item.get("lists") or []
    for entry in lists:
        heading = entry.get("text")
        content = [strip_html(point) for point in entry.get("content", []) if strip_html(point)]
        block = "\n".join([heading] + [f"- {point}" for point in content if point]) if heading else "\n".join(content)
        if block:
            parts.append(block)
    return "\n\n".join(part for part in parts if part).strip()


async def fetch_lever_jobs(source_token: str) -> tuple[str | None, list[ImportedJob]]:
    url = f"https://api.lever.co/v0/postings/{source_token}"
    async with _public_client() as client:
        response = await client.get(url, params={"mode": "json"})
    response.raise_for_status()

    items = response.json()
    jobs: list[ImportedJob] = []
    for item in items:
        categories = item.get("categories") or {}
        metadata = {
            "categories": categories,
            "workplaceType": item.get("workplaceType"),
            "team": item.get("categories", {}).get("team"),
            "department": item.get("categories", {}).get("department"),
        }
        jobs.append(
            ImportedJob(
                external_job_id=str(item.get("id")),
                url=item.get("hostedUrl") or item.get("applyUrl"),
                title=item.get("text") or "Untitled Job",
                company=source_token,
                description=_lever_description(item),
                location=categories.get("location"),
                employment_type=categories.get("commitment"),
                platform="lever",
                source_metadata=metadata,
            )
        )
    return source_token, jobs


async def fetch_ashby_jobs(source_token: str) -> tuple[str | None, list[ImportedJob]]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{source_token}"
    async with _public_client() as client:
        response = await client.get(url)
    response.raise_for_status()

    data = response.json()
    jobs: list[ImportedJob] = []
    for item in data.get("jobs", []):
        if item.get("isListed") is False:
            continue

        address = item.get("address") or {}
        postal_address = address.get("postalAddress") or {}
        metadata = {
            "department": item.get("department"),
            "team": item.get("team"),
            "workplaceType": item.get("workplaceType"),
            "isRemote": item.get("isRemote"),
            "secondaryLocations": item.get("secondaryLocations") or [],
            "publishedAt": item.get("publishedAt"),
            "applyUrl": item.get("applyUrl"),
            "addressCountry": postal_address.get("addressCountry"),
        }
        location = item.get("location")
        if not location:
            secondary_locations = [value for value in item.get("secondaryLocations") or [] if value]
            if secondary_locations:
                location = ", ".join(secondary_locations)

        jobs.append(
            ImportedJob(
                external_job_id=str(item.get("id")),
                url=item.get("jobUrl") or item.get("applyUrl"),
                title=item.get("title") or "Untitled Job",
                company=None,
                description=strip_html(item.get("descriptionPlain") or item.get("descriptionHtml")),
                location=location,
                employment_type=humanize_code(item.get("employmentType")),
                platform="ashby",
                source_metadata=metadata,
            )
        )
    return source_token, jobs


def _recruitee_description(item: dict) -> str:
    parts = [
        strip_html(item.get("description")),
        strip_html(item.get("requirements")),
    ]
    return "\n\n".join(part for part in parts if part).strip()


def _recruitee_location(item: dict) -> str | None:
    if item.get("location"):
        return item.get("location")
    parts = [item.get("city"), item.get("state_name"), item.get("country")]
    filtered: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if not part:
            continue
        normalized = str(part).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        filtered.append(normalized)
    return ", ".join(filtered) if filtered else None


async def fetch_recruitee_jobs(source_token: str) -> tuple[str | None, list[ImportedJob]]:
    url = f"https://{source_token}.recruitee.com/api/offers"
    async with _public_client() as client:
        response = await client.get(url)
    response.raise_for_status()

    data = response.json()
    offers = data.get("offers", [])
    company_name = next((offer.get("company_name") for offer in offers if offer.get("company_name")), source_token)
    jobs: list[ImportedJob] = []
    for item in offers:
        if item.get("status") and item.get("status") != "published":
            continue

        metadata = {
            "careers_apply_url": item.get("careers_apply_url"),
            "department": item.get("department"),
            "category_code": item.get("category_code"),
            "experience_code": item.get("experience_code"),
            "education_code": item.get("education_code"),
            "salary": item.get("salary"),
            "remote": item.get("remote"),
            "hybrid": item.get("hybrid"),
            "on_site": item.get("on_site"),
            "open_questions": item.get("open_questions") or [],
            "locations": item.get("locations") or [],
            "published_at": item.get("published_at"),
            "updated_at": item.get("updated_at"),
        }

        external_job_id = item.get("id") or item.get("guid") or item.get("slug")
        jobs.append(
            ImportedJob(
                external_job_id=str(external_job_id),
                url=item.get("careers_url") or item.get("careers_apply_url"),
                title=item.get("title") or item.get("sharing_title") or "Untitled Job",
                company=item.get("company_name") or company_name,
                description=_recruitee_description(item),
                location=_recruitee_location(item),
                employment_type=humanize_code(item.get("employment_type_code")),
                platform="recruitee",
                source_metadata=metadata,
            )
        )
    return company_name, jobs


async def fetch_jobs_for_source(source: JobSource) -> tuple[str | None, list[ImportedJob]]:
    if source.platform == "greenhouse":
        return await fetch_greenhouse_jobs(source.source_token)
    if source.platform == "lever":
        return await fetch_lever_jobs(source.source_token)
    if source.platform == "ashby":
        return await fetch_ashby_jobs(source.source_token)
    if source.platform == "recruitee":
        return await fetch_recruitee_jobs(source.source_token)
    raise JobSourceError(f"Unsupported source platform: {source.platform}")


def serialize_job(job: Job) -> JobRead:
    return JobRead(
        id=job.id,
        source_id=job.source_id,
        external_job_id=job.external_job_id,
        url=job.url,
        company=job.company,
        title=job.title,
        description=job.description,
        location=job.location,
        employment_type=job.employment_type,
        availability=job.availability,
        platform=job.platform,
        status=job.status,
        source_metadata=job.source_metadata,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def serialize_source(source: JobSource) -> JobSourceRead:
    return JobSourceRead(
        id=source.id,
        name=source.name,
        source_url=source.source_url,
        platform=source.platform,
        source_token=source.source_token,
        last_sync_at=source.last_sync_at,
        last_error=source.last_error,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


def resolve_source_payload(payload: JobSourceCreate) -> tuple[str, str]:
    platform = normalize_platform(payload.platform) if payload.platform else detect_platform_from_url(payload.source_url)
    token = extract_source_token(platform=platform, source_url=payload.source_url, source_token=payload.source_token)
    return platform, token


def refresh_source_identity_from_url(source: JobSource) -> None:
    if not source.source_url:
        return
    platform = detect_platform_from_url(source.source_url)
    token = extract_source_token(platform=platform, source_url=source.source_url, source_token=None)
    source.platform = platform
    source.source_token = token


async def create_or_get_source(session: Session, payload: JobSourceCreate) -> JobSource:
    platform, token = resolve_source_payload(payload)
    existing = (
        session.query(JobSource)
        .filter(JobSource.platform == platform, JobSource.source_token == token)
        .one_or_none()
    )
    if existing is not None:
        if payload.name:
            existing.name = payload.name
        if payload.source_url:
            existing.source_url = payload.source_url
        return existing

    existing_by_url = None
    if payload.source_url:
        existing_by_url = (
            session.query(JobSource)
            .filter(JobSource.platform == platform, JobSource.source_url == payload.source_url)
            .one_or_none()
        )
    if existing_by_url is not None:
        existing_by_url.source_token = token
        if payload.name:
            existing_by_url.name = payload.name
        return existing_by_url

    source = JobSource(
        name=payload.name or token,
        source_url=payload.source_url,
        platform=platform,
        source_token=token,
    )
    session.add(source)
    session.flush()
    return source


async def sync_job_source(session: Session, source: JobSource) -> JobSourceSyncRead:
    try:
        refresh_source_identity_from_url(source)
    except JobSourceError:
        pass

    try:
        resolved_name, imported_jobs = await fetch_jobs_for_source(source)
    except Exception as exc:
        source.last_error = str(exc)
        source.last_sync_at = utc_now()
        session.commit()
        raise

    if resolved_name and source.name == source.source_token:
        source.name = resolved_name

    existing_jobs = session.query(Job).filter(Job.source_id == source.id).all()
    existing_by_external_id = {job.external_job_id: job for job in existing_jobs if job.external_job_id}
    existing_by_url = {job.url: job for job in existing_jobs}

    imported_count = 0
    updated_count = 0
    closed_count = 0
    seen_job_ids: set[str] = set()

    for imported in imported_jobs:
        seen_job_ids.add(imported.external_job_id)
        job = existing_by_external_id.get(imported.external_job_id) or existing_by_url.get(imported.url)
        if job is None:
            job = Job(
                source_id=source.id,
                external_job_id=imported.external_job_id,
                url=imported.url,
                company=imported.company or source.name,
                title=imported.title,
                description=imported.description,
                location=imported.location,
                employment_type=imported.employment_type,
                availability="open",
                platform=imported.platform,
                status="queued",
                source_metadata=imported.source_metadata,
            )
            session.add(job)
            imported_count += 1
        else:
            job.source_id = source.id
            job.external_job_id = imported.external_job_id
            job.url = imported.url
            job.company = imported.company or job.company or source.name
            job.title = imported.title
            job.description = imported.description
            job.location = imported.location
            job.employment_type = imported.employment_type
            job.availability = "open"
            job.platform = imported.platform
            job.source_metadata = imported.source_metadata
            updated_count += 1

    for existing in existing_jobs:
        if existing.external_job_id and existing.external_job_id not in seen_job_ids and existing.availability != "closed":
            existing.availability = "closed"
            closed_count += 1

    source.last_error = None
    source.last_sync_at = utc_now()
    session.commit()
    session.refresh(source)

    open_jobs = (
        session.query(Job)
        .filter(Job.source_id == source.id, Job.availability == "open")
        .order_by(Job.created_at.desc())
        .all()
    )
    return JobSourceSyncRead(
        source=serialize_source(source),
        imported=imported_count,
        updated=updated_count,
        closed=closed_count,
        open_jobs=[serialize_job(job) for job in open_jobs],
    )

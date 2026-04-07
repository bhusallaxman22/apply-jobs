from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

from app.config import get_settings
from app.llm import request_json_completion
from app.schemas import ResumeCustomizeRequest, ResumeVariantRead, TailoredResumeDocument


class ResumeCustomizationError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "resume"


def safe_read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(page.strip() for page in pages if page.strip()).strip()


def load_resume_source(profile_data: dict[str, Any]) -> tuple[str, str]:
    documents = dict(profile_data.get("documents", {}))
    candidates = [
        documents.get("resume_markdown_path"),
        documents.get("resume_source_text_path"),
        documents.get("resume_typst_path"),
    ]

    for raw_path in candidates:
        if not raw_path:
            continue
        path = Path(raw_path)
        content = safe_read_text(path)
        if content:
            return content, str(path)

    pdf_path = documents.get("resume_pdf")
    if pdf_path:
        path = Path(pdf_path)
        if path.exists():
            try:
                text = extract_pdf_text(path)
            except Exception:
                text = ""
            if text:
                return text, str(path)

    raise ResumeCustomizationError("Profile does not have resume source content to tailor from.")


def build_job_context(
    *,
    job_url: str | None,
    company: str | None,
    job_title: str | None,
    job_description: str,
) -> dict[str, str | None]:
    return {
        "job_url": job_url,
        "company": company,
        "job_title": job_title,
        "job_description": job_description.strip(),
    }


def profile_snapshot(profile_data: dict[str, Any]) -> dict[str, Any]:
    scrubbed = deepcopy(profile_data)
    documents = dict(scrubbed.get("documents", {}))
    for key in ("resume_markdown_path", "resume_source_text_path", "resume_typst_path"):
        documents.pop(key, None)
    scrubbed["documents"] = documents
    return scrubbed


def generation_prompt(
    *,
    source_text: str,
    source_path: str,
    profile_data: dict[str, Any],
    job_context: dict[str, str | None],
) -> str:
    return f"""
Create a truthful, job-tailored resume from the provided source resume and profile data.

Rules:
- Return valid JSON only.
- Do not invent employers, dates, metrics, technologies, degrees, or achievements.
- You may reorder, compress, and rewrite existing content for clarity and fit.
- Prefer the most relevant skills, experience bullets, and projects for the target role.
- Keep the result concise and resume-appropriate.
- If a section does not have enough evidence, return an empty list.
- Review notes should explain what changed in 1 sentence each.

Job context:
{json.dumps(job_context, indent=2)}

Profile data:
{json.dumps(profile_snapshot(profile_data), indent=2)}

Resume source path:
{source_path}

Resume source content:
{source_text[:12000]}

Output schema:
{{
  "summary": "string",
  "skills": [{{"category": "string", "items": ["string"]}}],
  "experience": [
    {{
      "company": "string",
      "role": "string",
      "location": "string",
      "dates": "string",
      "bullets": ["string"]
    }}
  ],
  "projects": [
    {{
      "name": "string",
      "url": "string",
      "bullets": ["string"],
      "technologies": ["string"]
    }}
  ],
  "education": [
    {{
      "institution": "string",
      "degree": "string",
      "dates": "string",
      "details": ["string"]
    }}
  ],
  "achievements": ["string"],
  "review_notes": ["string"]
}}
""".strip()


async def generate_tailored_resume_document(
    profile_data: dict[str, Any],
    job_context: dict[str, str | None],
) -> tuple[TailoredResumeDocument, str]:
    source_text, source_path = load_resume_source(profile_data)
    raw = await request_json_completion(
        system_prompt="You write accurate resumes. Return JSON only.",
        user_prompt=generation_prompt(
            source_text=source_text,
            source_path=source_path,
            profile_data=profile_data,
            job_context=job_context,
        ),
        temperature=0.2,
    )
    return TailoredResumeDocument.model_validate(raw), source_path


def render_resume_markdown(document: TailoredResumeDocument, profile_data: dict[str, Any]) -> str:
    identity = dict(profile_data.get("identity", {}))
    lines = ["# Tailored Resume", ""]

    if identity.get("full_name"):
        lines.extend([f"## {identity['full_name']}", ""])

    contact_parts = [identity.get("email"), identity.get("phone"), identity.get("location")]
    contact_line = " | ".join(part for part in contact_parts if part)
    if contact_line:
        lines.extend([contact_line, ""])

    lines.extend(["# Summary", document.summary, ""])

    if document.skills:
        lines.append("# Skills")
        for group in document.skills:
            lines.append(f"- **{group.category}:** {', '.join(group.items)}")
        lines.append("")

    if document.experience:
        lines.append("# Experience")
        for item in document.experience:
            heading = " | ".join(part for part in [item.role, item.company, item.location, item.dates] if part)
            lines.append(f"## {heading}")
            for bullet in item.bullets:
                lines.append(f"- {bullet}")
            lines.append("")

    if document.projects:
        lines.append("# Projects")
        for item in document.projects:
            lines.append(f"## {item.name}")
            if item.url:
                lines.append(f"- URL: {item.url}")
            for bullet in item.bullets:
                lines.append(f"- {bullet}")
            if item.technologies:
                lines.append(f"- Technologies: {', '.join(item.technologies)}")
            lines.append("")

    if document.education:
        lines.append("# Education")
        for item in document.education:
            heading = " | ".join(part for part in [item.institution, item.degree, item.dates] if part)
            lines.append(f"## {heading}")
            for detail in item.details:
                lines.append(f"- {detail}")
            lines.append("")

    if document.achievements:
        lines.append("# Achievements")
        for achievement in document.achievements:
            lines.append(f"- {achievement}")
        lines.append("")

    if document.review_notes:
        lines.append("# Review Notes")
        for note in document.review_notes:
            lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def pdf_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ResumeTitle",
            parent=base["Title"],
            fontSize=18,
            leading=22,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#0b4f7a"),
            spaceAfter=8,
        ),
        "contact": ParagraphStyle(
            "ResumeContact",
            parent=base["Normal"],
            fontSize=9,
            leading=11,
            alignment=TA_CENTER,
            spaceAfter=6,
        ),
        "section": ParagraphStyle(
            "ResumeSection",
            parent=base["Heading2"],
            fontSize=12,
            leading=14,
            textColor=colors.HexColor("#0b4f7a"),
            spaceBefore=8,
            spaceAfter=6,
        ),
        "subhead": ParagraphStyle(
            "ResumeSubhead",
            parent=base["Heading4"],
            fontSize=10,
            leading=12,
            spaceBefore=4,
            spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "ResumeBody",
            parent=base["BodyText"],
            fontSize=9.5,
            leading=12,
            spaceAfter=4,
        ),
    }


def bullet_list(items: list[str], style: ParagraphStyle):
    if not items:
        return []
    return [ListFlowable([ListItem(Paragraph(item, style)) for item in items], bulletType="bullet", leftIndent=14)]


def render_resume_pdf(document: TailoredResumeDocument, profile_data: dict[str, Any], output_path: Path) -> None:
    identity = dict(profile_data.get("identity", {}))
    styles = pdf_styles()
    story = []

    story.append(Paragraph(identity.get("full_name", "Tailored Resume"), styles["title"]))

    contact_parts = [identity.get("email"), identity.get("phone"), identity.get("location")]
    links = [identity.get("linkedin"), identity.get("github"), identity.get("portfolio")]
    contact_line = " | ".join(part for part in contact_parts if part)
    links_line = " | ".join(part for part in links if part)
    if contact_line:
        story.append(Paragraph(contact_line, styles["contact"]))
    if links_line:
        story.append(Paragraph(links_line, styles["contact"]))

    story.append(Paragraph("Summary", styles["section"]))
    story.append(Paragraph(document.summary, styles["body"]))

    if document.skills:
        story.append(Paragraph("Skills", styles["section"]))
        for group in document.skills:
            story.append(Paragraph(f"<b>{group.category}:</b> {', '.join(group.items)}", styles["body"]))

    if document.experience:
        story.append(Paragraph("Experience", styles["section"]))
        for item in document.experience:
            header = " | ".join(part for part in [item.role, item.company, item.location, item.dates] if part)
            story.append(Paragraph(header, styles["subhead"]))
            story.extend(bullet_list(item.bullets, styles["body"]))
            story.append(Spacer(1, 0.08 * inch))

    if document.projects:
        story.append(Paragraph("Projects", styles["section"]))
        for item in document.projects:
            story.append(Paragraph(item.name, styles["subhead"]))
            if item.url:
                story.append(Paragraph(item.url, styles["body"]))
            story.extend(bullet_list(item.bullets, styles["body"]))
            if item.technologies:
                story.append(Paragraph(f"<b>Technologies:</b> {', '.join(item.technologies)}", styles["body"]))
            story.append(Spacer(1, 0.08 * inch))

    if document.education:
        story.append(Paragraph("Education", styles["section"]))
        for item in document.education:
            header = " | ".join(part for part in [item.institution, item.degree, item.dates] if part)
            story.append(Paragraph(header, styles["subhead"]))
            story.extend(bullet_list(item.details, styles["body"]))

    if document.achievements:
        story.append(Paragraph("Achievements", styles["section"]))
        story.extend(bullet_list(document.achievements, styles["body"]))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
    )
    doc.build(story)


async def create_resume_variant(
    *,
    profile_id: str,
    profile_data: dict[str, Any],
    job_request: ResumeCustomizeRequest,
) -> ResumeVariantRead:
    job_context = build_job_context(
        job_url=job_request.job_url,
        company=job_request.company,
        job_title=job_request.job_title,
        job_description=job_request.job_description,
    )
    document, source_path = await generate_tailored_resume_document(profile_data, job_context)

    settings = get_settings()
    variant_dir = settings.resume_variants_path / profile_id
    variant_dir.mkdir(parents=True, exist_ok=True)

    descriptor = "-".join(
        part for part in [job_request.company or "", job_request.job_title or "customized-resume"] if part
    )
    filename_slug = slugify(descriptor)
    timestamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    markdown_path = variant_dir / f"{timestamp}-{filename_slug}.md"
    pdf_path = variant_dir / f"{timestamp}-{filename_slug}.pdf"

    rendered_markdown = render_resume_markdown(document, profile_data)
    markdown_path.write_text(rendered_markdown, encoding="utf-8")
    render_resume_pdf(document, profile_data, pdf_path)

    return ResumeVariantRead(
        profile_id=profile_id,
        job_url=job_request.job_url,
        company=job_request.company,
        job_title=job_request.job_title,
        markdown_path=str(markdown_path),
        pdf_path=str(pdf_path),
        source_path=source_path,
        rendered_markdown=rendered_markdown,
        review_notes=document.review_notes,
        generated_at=utc_now(),
    )

import logging
import asyncio
import base64
from playwright.sync_api import sync_playwright

from backend.models.resume import ParsedResume
from backend.models.schemas import OptimizationRequest, OptimizationResponse
from backend.agents.resume_optimization_agent import run_resume_optimization
from backend.services.resume_renderer import render_resume_to_html
from backend.services.job_context import resolve_job_text
from backend.services.ats_scoring import extract_optimized_projects, verify_experience_grounding
from backend.db.supabase_client import (
    get_job_by_id,
    get_job_fit_analysis,
    get_profile_updated_at,
    get_profile_data,
    upsert_optimized_resume_snapshot,
)

logger = logging.getLogger(__name__)

def _compile_html_to_pdf_sync(html_content: str) -> str | None:
    """Synchronous PDF generation using Playwright's sync API.
    
    Run in a separate thread to avoid Windows event loop subprocess conflicts.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content(html_content, wait_until='networkidle')
            pdf_bytes = page.pdf(format='A4', print_background=True)
            browser.close()
            return base64.b64encode(pdf_bytes).decode('utf-8')
    except Exception as e:
        logger.error(f"Error compiling HTML to PDF: {e}")
        return None

async def compile_html_to_pdf_base64(html_content: str) -> str | None:
    """Offload PDF generation to a thread to avoid async event loop issues on Windows."""
    return await asyncio.to_thread(_compile_html_to_pdf_sync, html_content)


def _get_fresh_cached_resume(user_id: str, job_id: str) -> ParsedResume | None:
    """
    Returns the tailored resume cached by a prior "Analyze fit" call for this
    (user, job) pair, unless the profile has since changed (re-uploaded resume).
    """
    cached = get_job_fit_analysis(user_id, job_id)
    if not cached or not cached.get("optimized_resume_json"):
        return None

    profile_updated_at = get_profile_updated_at(user_id)
    if profile_updated_at and profile_updated_at > cached.get("updated_at", ""):
        return None

    try:
        return ParsedResume(**cached["optimized_resume_json"])
    except Exception:
        logger.exception("Cached optimized resume failed to parse for user_id=%s job_id=%s", user_id, job_id)
        return None


def _verify_experience(optimized_resume: ParsedResume, profile_data: dict | None) -> None:
    """Replaces ungrounded rewritten responsibilities with the user's own before the
    tailored resume is rendered or cached."""
    original_experience = (profile_data or {}).get("original_resume", {}).get("experience", [])
    if not original_experience:
        return
    optimized_resume.experience = verify_experience_grounding(
        original_experience, optimized_resume.experience
    )


def _persist_optimized_resume(
    user_id: str, job_id: str, optimized_resume: ParsedResume, profile_data: dict | None = None
) -> None:
    """Caches the tailored resume + derived per-project bullets for reuse across the
    'Analyze fit' and 'Generate Optimized Resume' flows."""
    if profile_data is None:
        profile_data = get_profile_data(user_id)
    original_projects = (profile_data or {}).get("original_resume", {}).get("projects", [])
    optimized_projects = extract_optimized_projects(original_projects, optimized_resume.projects)
    try:
        upsert_optimized_resume_snapshot(
            user_id,
            job_id,
            optimized_resume.model_dump(),
            [p.model_dump() for p in optimized_projects],
        )
    except Exception:
        # Caching is a best-effort optimization; don't fail the PDF flow over it.
        logger.warning("Failed to cache optimized resume for user_id=%s job_id=%s", user_id, job_id)

async def optimize_resume_service(request: OptimizationRequest) -> OptimizationResponse:
    logger.info("Processing optimization request for user_id=%s", request.user_id)

    job_title = request.job_title
    job_description = request.job_description
    job = None

    # Prefer resolving the job server-side by id (the job-card "Generate Resume"
    # flow) rather than trusting client-supplied title/description text.
    if request.job_id:
        job = get_job_by_id(request.job_id)
        if not job:
            return OptimizationResponse(
                success=False,
                message="Job not found.",
            )
        job_title, job_description = resolve_job_text(job)

    if not job_title or not job_description:
        return OptimizationResponse(
            success=False,
            message="A job_id or both job_title and job_description are required.",
        )

    # If "Analyze fit" already tailored this resume for this job (and the profile
    # hasn't changed since), reuse it instead of paying for a second LLM call.
    optimized_resume = None
    if request.job_id:
        optimized_resume = _get_fresh_cached_resume(request.user_id, request.job_id)

    if optimized_resume is None:
        # 1. Run LLM Agent to optimize resume
        optimized_resume = await run_resume_optimization(
            user_id=request.user_id,
            job_title=job_title,
            job_description=job_description,
            # Lets the agent reuse the ATS keyword classification cached by an
            # earlier "Analyze fit" for this job instead of re-running it.
            job_id=request.job_id,
        )

        if not optimized_resume:
            return OptimizationResponse(
                success=False,
                message="Failed to optimize resume. Check logs for details."
            )

        profile_data = get_profile_data(request.user_id)
        _verify_experience(optimized_resume, profile_data)

        if request.job_id:
            _persist_optimized_resume(
                request.user_id, request.job_id, optimized_resume, profile_data
            )

    # 2. Render optimized resume to HTML using standard template
    html_content = render_resume_to_html(optimized_resume)
    
    if not html_content:
        return OptimizationResponse(
            success=False,
            message="Failed to render HTML template. Check logs for details."
        )

    # 3. Compile HTML to PDF
    pdf_content = await compile_html_to_pdf_base64(html_content)

    return OptimizationResponse(
        success=True,
        message="Resume optimized successfully.",
        optimized_resume_json=optimized_resume.model_dump(),
        html_content=html_content,
        pdf_content=pdf_content
    )

import logging
import asyncio
import base64
from playwright.sync_api import sync_playwright

from backend.models.schemas import OptimizationRequest, OptimizationResponse
from backend.agents.resume_optimization_agent import run_resume_optimization
from backend.services.resume_renderer import render_resume_to_html

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

async def optimize_resume_service(request: OptimizationRequest) -> OptimizationResponse:
    logger.info("Processing optimization request for user_id=%s", request.user_id)
    
    # 1. Run LLM Agent to optimize resume
    optimized_resume = await run_resume_optimization(
        user_id=request.user_id,
        job_title=request.job_title,
        job_description=request.job_description
    )
    
    if not optimized_resume:
        return OptimizationResponse(
            success=False,
            message="Failed to optimize resume. Check logs for details."
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

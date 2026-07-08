import os
import logging
from jinja2 import Environment, FileSystemLoader

from backend.models.resume import ParsedResume

logger = logging.getLogger(__name__)

template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
# Using standard Jinja2 syntax which handles HTML perfectly
env = Environment(
    loader=FileSystemLoader(template_dir),
    autoescape=False
)

def render_resume_to_html(resume: ParsedResume) -> str | None:
    """
    Renders the parsed resume to an HTML string using the template.
    """
    try:
        template = env.get_template('resume_template.html')
        html_str = template.render(resume=resume)
        return html_str
    except Exception as e:
        logger.error("Failed to render HTML template: %s", e)
        return None

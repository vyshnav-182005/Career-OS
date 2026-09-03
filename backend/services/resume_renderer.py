import os
import logging
from dataclasses import dataclass, asdict

from jinja2 import Environment, FileSystemLoader

from backend.models.resume import ParsedResume

logger = logging.getLogger(__name__)

template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
# Using standard Jinja2 syntax which handles HTML perfectly
env = Environment(
    loader=FileSystemLoader(template_dir),
    autoescape=False
)

# Characters of body text that fit on one printed line at the baseline font
# size and page width; anything longer wraps and costs another line.
CHARS_PER_LINE = 105


@dataclass(frozen=True)
class Density:
    """Typography/spacing settings the template turns into CSS variables."""
    font_size: float
    line_height: float
    section_gap: int
    item_gap: int
    margin_v: int
    margin_h: int


# Sparse content: larger type, generous spacing and wider margins (which also
# narrow the text column, so lines wrap sooner) push a short resume down to the
# bottom of the page instead of leaving it trailing off halfway.
DENSITY_RELAXED = Density(
    font_size=11.8, line_height=1.55, section_gap=18, item_gap=13, margin_v=19, margin_h=18
)
# The common case.
DENSITY_BALANCED = Density(
    font_size=11.0, line_height=1.42, section_gap=14, item_gap=10, margin_v=15, margin_h=15
)
# Content-heavy: tighten type, spacing and margins so a full resume still lands
# on one page. Past roughly 1.4x a page's worth of content, no preset can save
# it without deleting the user's material - that correctly runs to two pages.
DENSITY_COMPACT = Density(
    font_size=9.7, line_height=1.22, section_gap=9, item_gap=5, margin_v=10, margin_h=11
)


def _wrapped_lines(text: str) -> int:
    """How many printed lines a string occupies, accounting for wrapping."""
    if not text:
        return 0
    return max(1, -(-len(text) // CHARS_PER_LINE))  # ceil division


def _count_content_lines(resume: ParsedResume) -> int:
    """
    Estimates how many printed lines the resume's content needs. Counts what
    actually consumes vertical space - bullets (wrapped), item headers, section
    headers - rather than raw character count, which over-weights a long
    summary and under-weights many short bullets.
    """
    lines = 0

    if resume.personal_info:
        lines += 3  # name + contact line + breathing room
        if resume.personal_info.summary:
            lines += _wrapped_lines(resume.personal_info.summary) + 1

    if resume.experience:
        lines += 2  # section header
        for exp in resume.experience:
            lines += 1  # title/company/date row
            if exp.location:
                lines += 1
            for resp in exp.responsibilities:
                lines += _wrapped_lines(resp)

    if resume.projects:
        lines += 2
        for proj in resume.projects:
            lines += 1
            if proj.technologies:
                lines += 1
            for bullet in proj.description:
                lines += _wrapped_lines(bullet)

    if resume.education:
        lines += 2
        for edu in resume.education:
            lines += 2  # institution row + degree subtitle
            if edu.description:
                lines += _wrapped_lines(edu.description)

    if resume.skills:
        lines += 2
        for category in resume.skills:
            if category.skills:
                lines += _wrapped_lines(", ".join(category.skills))

    if resume.certifications:
        lines += 2 + len(resume.certifications)

    if resume.publications:
        lines += 2 + 2 * len(resume.publications)

    for section in resume.custom_sections:
        if section.items:
            lines += 2 + 2 * len(section.items)

    if resume.languages:
        lines += 3

    return lines


# Share of the printable page the output aims to occupy. Just under full: a
# resume that renders to exactly 100% in one browser spills a stray line into a
# second page in another, where font metrics differ by a fraction of a percent.
TARGET_PAGE_FILL = 0.90

# Anchors calibrated by rendering this template in headless Chromium across a
# grid of content volumes: page fill is proportional to the estimated line
# count, fill ~= k * lines (measured intercept ~0), with k per preset:
#   RELAXED 0.0313 | BALANCED 0.0234 | COMPACT 0.0165
# Re-measure these if the template's base metrics change materially.
_DENSITY_ANCHORS = [
    (0.01654, DENSITY_COMPACT),
    (0.02338, DENSITY_BALANCED),
    (0.03130, DENSITY_RELAXED),
]


def _interpolate(low: Density, high: Density, t: float) -> Density:
    def mix(a: float, b: float) -> float:
        return a + (b - a) * t

    return Density(
        font_size=round(mix(low.font_size, high.font_size), 2),
        line_height=round(mix(low.line_height, high.line_height), 3),
        section_gap=round(mix(low.section_gap, high.section_gap)),
        item_gap=round(mix(low.item_gap, high.item_gap)),
        margin_v=round(mix(low.margin_v, high.margin_v)),
        margin_h=round(mix(low.margin_h, high.margin_h)),
    )


def compute_density(resume: ParsedResume) -> Density:
    """
    Picks the typography that makes this resume's content fill about one page.

    Solves for the scale whose measured fill-per-line hits TARGET_PAGE_FILL at
    this resume's estimated line count, then interpolates between the calibrated
    anchors — a step scale would leave content volumes between two presets
    either half-empty or one line over. Clamped at both ends: a genuinely thin
    resume is left under-filled rather than blown up to a comical font size, and
    a resume with well over a page of content runs to a second page rather than
    being shrunk past readability.

    Pure and browser-free, so it is unit-testable on its own.
    """
    lines = _count_content_lines(resume)
    if lines <= 0:
        return DENSITY_RELAXED

    needed_k = TARGET_PAGE_FILL / lines
    lowest_k, densest = _DENSITY_ANCHORS[0]
    highest_k, airiest = _DENSITY_ANCHORS[-1]
    if needed_k <= lowest_k:
        return densest
    if needed_k >= highest_k:
        return airiest

    for (k_low, d_low), (k_high, d_high) in zip(_DENSITY_ANCHORS, _DENSITY_ANCHORS[1:]):
        if k_low <= needed_k <= k_high:
            t = (needed_k - k_low) / (k_high - k_low)
            return _interpolate(d_low, d_high, t)

    return DENSITY_BALANCED


def render_resume_to_html(resume: ParsedResume) -> str | None:
    """
    Renders the parsed resume to an HTML string using the template, sized so
    the output fills roughly one page without padding it with whitespace.
    """
    try:
        template = env.get_template('resume_template.html')
        html_str = template.render(resume=resume, density=asdict(compute_density(resume)))
        return html_str
    except Exception as e:
        logger.error("Failed to render HTML template: %s", e)
        return None

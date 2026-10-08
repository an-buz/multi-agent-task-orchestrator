"""Downloadable public run results, with escaped and paginated PDF reports."""

import asyncio
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Literal
from xml.sax.saxutils import escape

from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFError, TTFont
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer

from app.core.config import get_settings
from app.schemas.run import RunRead
from app.services.runs import RunError

ExportFormat = Literal["json", "md", "pdf"]
_font_lock = Lock()


def render_pdf(report: str, font_path: Path) -> bytes:
    """Render text without interpreting untrusted HTML or fetching external assets."""
    font_name = "RunReport-" + sha256(str(font_path).encode()).hexdigest()[:16]
    try:
        with _font_lock:
            if font_name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
    except (OSError, ValueError, TTFError) as error:
        raise RunError("PDF font is unavailable. Configure EXPORT_PDF_FONT_PATH.", 503) from error
    body = ParagraphStyle("Body", fontName=font_name, fontSize=10, leading=15)
    heading = ParagraphStyle("Heading", parent=body, fontSize=14, leading=20, spaceAfter=8)
    story: list[Flowable] = []
    for line in report.splitlines():
        if not line.strip():
            story.append(Spacer(1, 8))
        else:
            is_heading = line.startswith("#")
            text = line.lstrip("# ") if is_heading else line
            story.append(Paragraph(escape(text), heading if is_heading else body))
    output = BytesIO()
    SimpleDocTemplate(output, title="Workflow run report").build(story)
    return output.getvalue()


async def export_result(run: RunRead, format: ExportFormat) -> tuple[bytes, str]:
    if run.status != "COMPLETED" or not run.final_report:
        raise RunError("Results can only be exported after the run completes.")
    if format == "json":
        return run.model_dump_json(indent=2).encode("utf-8"), "application/json"
    if format == "md":
        return run.final_report.encode("utf-8"), "text/markdown"
    return (
        await asyncio.to_thread(render_pdf, run.final_report, get_settings().export_pdf_font_path),
        "application/pdf",
    )

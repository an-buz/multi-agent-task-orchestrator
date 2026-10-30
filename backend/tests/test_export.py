"""Regression coverage for valid downloads, Unicode PDFs and terminal-state gates."""

import json
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.api.v1.runs import get_run_service
from app.core.config import get_settings
from app.main import app
from app.schemas.run import RunRead
from app.services.export import export_result, render_pdf
from app.services.runs import RunError, RunService
from fastapi.testclient import TestClient
from pypdf import PdfReader


def completed_run() -> RunRead:
    return RunRead(
        id=uuid4(),
        workflow_id=uuid4(),
        workflow_title="Test workflow",
        task="Export review",
        context_text="",
        status="COMPLETED",
        plan=None,
        final_report="## Result\n\nПеревірка звіту <safe> & data\n\n" + "Long report text.\n" * 160,
        total_tokens=13,
        total_time_ms=20,
        created_at=datetime.now(UTC),
        started_at=None,
        finished_at=None,
    )


async def test_export_formats_preserve_report_and_paginate_unicode_pdf() -> None:
    run = completed_run()

    content, media = await export_result(run, "json")

    assert media == "application/json"
    assert json.loads(content)["total_tokens"] == 13
    assert "planner_config" not in json.loads(content)

    content, media = await export_result(run, "md")

    assert media == "text/markdown"
    assert content.decode() == run.final_report

    content, media = await export_result(run, "pdf")

    assert media == "application/pdf"

    pdf = PdfReader(BytesIO(content))

    assert len(pdf.pages) > 1

    text = "".join(page.extract_text() for page in pdf.pages)

    assert "Перевірка звіту <safe> & data" in text


async def test_export_rejects_unfinished_run() -> None:
    run = completed_run().model_copy(update={"status": "AWAITING_CONFIRMATION"})

    with pytest.raises(RunError, match="after the run completes"):
        await export_result(run, "json")


def test_export_http_returns_attachment_and_rejects_unknown_format() -> None:
    run = completed_run()
    service = AsyncMock(spec=RunService)
    service.read.return_value = run
    app.dependency_overrides[get_run_service] = lambda: service

    try:
        with TestClient(app) as client:
            for format in ("json", "md", "pdf"):
                response = client.get(f"/api/v1/runs/{run.id}/export?format={format}")

                assert response.status_code == 200
                assert response.headers["content-disposition"] == (
                    f'attachment; filename="run-{run.id}.{format}"'
                )
                assert response.content

            assert client.get(f"/api/v1/runs/{run.id}/export?format=exe").status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_pdf_markdown_blocks_and_untrusted_markup() -> None:
    report = (
        "# Completed task\n\n## Results\n\n"
        "**Verified** and *reviewed* with `inline code`.\n\n"
        "- First item\n1. Ordered item\n\n"
        "| Check | Result |\n| --- | --- |\n| Unicode | Перевірено |\n\n"
        "```python\n# This is code, not a heading\n    print('<safe> & value')\n```\n\n"
        '[Source](https://example.com)\n<img src="https://invalid.example/private"/>\n'
    )
    pdf = PdfReader(BytesIO(render_pdf(report, get_settings().export_pdf_font_path)))
    text = "\n".join(page.extract_text() for page in pdf.pages)

    assert "Verified and reviewed with inline code." in text
    assert "**Verified**" not in text
    assert "Перевірено" in text
    assert "| --- |" not in text
    assert "# This is code, not a heading" in text
    assert "print('<safe> & value')" in text
    assert "Source (https://example.com)" in text
    assert '<img src="https://invalid.example/private"/>' in text
    assert "Page 1" in text
    assert not pdf.pages[0].get("/Annots")


def test_pdf_long_table_cells_code_and_unbroken_words_paginate() -> None:
    report = (
        "# Large report\n\n| Item | Detail |\n| --- | --- |\n"
        "| Long cell | " + "Cell content. " * 800 + " |\n\n"
        "```\n" + "    code line\n" * 130 + "```\n\n" + "x" * 1500 + "\nEnd of report"
    )
    pdf = PdfReader(BytesIO(render_pdf(report, get_settings().export_pdf_font_path)))
    text = "\n".join(page.extract_text() for page in pdf.pages)

    assert len(pdf.pages) > 3
    assert "End of report" in text
    assert text.count("code line") == 130

    for number, page in enumerate(pdf.pages, 1):
        assert f"Page {number}" in page.extract_text()


def test_pdf_missing_font_returns_actionable_error(tmp_path: Path) -> None:
    with pytest.raises(RunError, match="EXPORT_PDF_FONT_PATH"):
        render_pdf("# Report", tmp_path / "missing.ttf")

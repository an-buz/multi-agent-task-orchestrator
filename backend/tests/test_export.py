"""Regression coverage for valid downloads, Unicode PDFs and terminal-state gates."""

import json
from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.api.v1.runs import get_run_service
from app.main import app
from app.schemas.run import RunRead
from app.services.export import export_result
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

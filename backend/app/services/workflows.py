"""Workflow deletion rules independent of HTTP."""

from uuid import UUID

from app.core.errors import AppError
from app.db.workflow_repository import WorkflowRepository


class WorkflowError(AppError):
    def __init__(self, message: str, code: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class WorkflowService:
    def __init__(self, repository: WorkflowRepository) -> None:
        self.repository = repository

    async def delete(self, workflow_id: UUID) -> None:
        workflow = await self.repository.get_for_deletion(workflow_id)
        if workflow is None:
            raise WorkflowError("Workflow not found.", "workflow_not_found", 404)
        if await self.repository.has_runs(workflow_id):
            raise WorkflowError(
                "Delete this workflow's runs from the Runs page before deleting the workflow.",
                "workflow_has_runs",
                409,
            )
        await self.repository.delete(workflow)

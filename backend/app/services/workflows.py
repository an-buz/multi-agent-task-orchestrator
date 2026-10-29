"""Workflow validation and CRUD rules independent of HTTP."""

from uuid import UUID

from app.core.errors import AppError
from app.db.workflow_repository import WorkflowRepository
from app.models.workflow import Workflow
from app.schemas.workflow import WorkflowRead, WorkflowWrite, validate_workflow_graph


class WorkflowError(AppError):
    def __init__(
        self, message: str, code: str, status_code: int, details: dict[str, object] | None = None
    ) -> None:
        super().__init__(message, details)

        self.code = code
        self.status_code = status_code


class WorkflowService:
    def __init__(self, repository: WorkflowRepository) -> None:
        self.repository = repository

    async def validate(self, payload: WorkflowWrite) -> None:
        errors = validate_workflow_graph(payload)

        agent_ids = {step.agent_id for step in payload.steps}
        missing = agent_ids - await self.repository.agent_ids(agent_ids)

        if missing:
            errors.append(f"unknown agent IDs: {', '.join(sorted(map(str, missing)))}")

        if errors:
            raise WorkflowError("Invalid workflow.", "invalid_workflow", 422, {"errors": errors})

    async def require(self, workflow_id: UUID, *, lock: bool = False) -> Workflow:
        workflow = (
            await self.repository.get_for_deletion(workflow_id)
            if lock
            else await self.repository.get(workflow_id)
        )

        if workflow is None:
            raise WorkflowError("Workflow not found.", "workflow_not_found", 404)

        return workflow

    async def read(self, workflow_id: UUID) -> WorkflowRead:
        return WorkflowRead.model_validate(await self.require(workflow_id))

    async def list(self, limit: int, offset: int) -> dict[str, object]:
        workflows, total = await self.repository.list(limit, offset)

        return {"items": [WorkflowRead.model_validate(item) for item in workflows], "total": total}

    async def create(self, payload: WorkflowWrite) -> WorkflowRead:
        await self.validate(payload)

        workflow = Workflow(**payload.model_dump(mode="json"))

        await self.repository.save(workflow)

        return WorkflowRead.model_validate(workflow)

    async def update(self, workflow_id: UUID, payload: WorkflowWrite) -> WorkflowRead:
        workflow = await self.require(workflow_id, lock=True)

        await self.validate(payload)

        for field, value in payload.model_dump(mode="json").items():
            setattr(workflow, field, value)

        await self.repository.save(workflow)

        return WorkflowRead.model_validate(workflow)

    async def delete(self, workflow_id: UUID) -> None:
        workflow = await self.require(workflow_id, lock=True)

        if await self.repository.has_runs(workflow_id):
            raise WorkflowError(
                "Delete this workflow's runs from the Runs page before deleting the workflow.",
                "workflow_has_runs",
                409,
            )

        await self.repository.delete(workflow)

"""Deterministic completion reports from persisted execution data."""

from app.models.run import Run
from app.models.run_step import RunStep
from app.schemas.run import RunPlan


def build_report(run: Run, steps: dict[int, RunStep]) -> str:
    """Preserve plan order and original outputs without inventing a synthesis."""

    plan = RunPlan.model_validate(run.plan)
    sections = [
        "# Workflow run report",
        "## Execution summary\n\n"
        f"- Run: `{run.id}`\n"
        f"- Status: {run.status}\n"
        f"- Completed steps: {len(plan.steps)}\n"
        f"- Total tokens (including planning): {run.total_tokens:,}\n"
        f"- Processing time (planning + steps): {run.total_time_ms:,} ms\n"
        f"- Planning tokens: {run.planning_prompt_tokens + run.planning_completion_tokens:,}",
        f"## Original task\n\n{run.task}",
        f"## Plan\n\n{plan.summary}",
        "## Step results\n\n"
        "The following sections contain the original agent outputs in plan order.",
    ]

    for planned in plan.steps:
        step = steps[planned.step_number]
        dependencies = ", ".join(str(number) for number in step.depends_on) or "None"
        sections.append(
            f"## Step {step.step_number}: {step.agent_name}\n\n"
            f"- Status: {step.status}\n"
            f"- Dependencies: {dependencies}\n"
            f"- Tokens: {step.tokens_prompt + step.tokens_completion:,} "
            f"(input: {step.tokens_prompt:,}; output: {step.tokens_completion:,})\n"
            f"- Processing time: {step.execution_time_ms:,} ms\n"
            f"- Attempts: {step.attempt}\n\n"
            f"### Assigned task\n\n{step.subtask}\n\n"
            f"### Agent output\n\n{step.output or 'No text output was returned.'}"
        )

    return "\n\n".join(sections)

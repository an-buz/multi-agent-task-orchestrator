import type { RunDetails, RunEvent, RunStep } from "./types";

export function runSteps(run: RunDetails | undefined): RunStep[] {
  return run?.plan ? (Array.isArray(run.plan) ? run.plan : run.plan.steps) : [];
}

export function eventKey(event: RunEvent): string {
  return event.id ?? JSON.stringify(event);
}

export function applyStreamChunk(
  run: RunDetails | undefined,
  event: RunEvent,
): RunDetails | undefined {
  const data = event.data ?? event.payload;
  if (
    !run?.plan ||
    event.event !== "agent:stream_chunk" ||
    !data ||
    typeof data.stepNumber !== "number" ||
    typeof data.output !== "string" ||
    typeof data.attempt !== "number" ||
    !Number.isInteger(data.attempt) ||
    data.attempt < 0
  )
    return run;
  const { stepNumber, output, attempt } = data;
  let changed = false;
  const steps = runSteps(run).map((step) => {
    if (
      step.step_number !== stepNumber ||
      (step.attempt ?? 0) > attempt ||
      (["COMPLETED", "FAILED", "CANCELLED"].includes(step.status) && (step.attempt ?? 0) >= attempt)
    )
      return step;
    if (step.status === "IN_PROGRESS" && step.attempt === attempt && step.output === output)
      return step;
    changed = true;
    return { ...step, status: "IN_PROGRESS" as const, attempt, output };
  });
  return changed ? { ...run, plan: Array.isArray(run.plan) ? steps : { ...run.plan, steps } } : run;
}

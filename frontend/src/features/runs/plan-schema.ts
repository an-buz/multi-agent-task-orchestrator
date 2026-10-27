import { z } from "zod";
import type { RunStep } from "./types";

export const planSchema = z.object({
  tasks: z.array(z.object({ task: z.string().trim().min(1, "Enter a task.") })).min(1),
  expected_subtasks: z.record(z.string(), z.string()),
});

export type PlanFormValues = z.infer<typeof planSchema>;

export function planFormValues(steps: RunStep[]): PlanFormValues {
  return {
    tasks: steps.map((step) => ({ task: step.subtask ?? step.input ?? "" })),
    expected_subtasks: Object.fromEntries(
      steps.map((step) => [step.step_number, step.subtask ?? step.input ?? ""]),
    ),
  };
}

export function samePlanTasks(
  left: Record<string, string>,
  right: Record<string, string>,
): boolean {
  return (
    Object.keys(left).length === Object.keys(right).length &&
    Object.entries(left).every(([number, task]) => right[number] === task)
  );
}

export function editedPlanSteps(steps: RunStep[], values: PlanFormValues): RunStep[] {
  return steps.map((step, index) => ({
    ...step,
    input: values.tasks[index].task,
    subtask: values.tasks[index].task,
  }));
}

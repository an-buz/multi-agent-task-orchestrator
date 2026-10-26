import { z } from "zod";
import type { RunStep } from "./types";

export const planSchema = z.object({
  tasks: z.array(z.object({ task: z.string().trim().min(1, "Enter a task.") })).min(1),
});

export type PlanFormValues = z.infer<typeof planSchema>;

export function planFormValues(steps: RunStep[]): PlanFormValues {
  return { tasks: steps.map((step) => ({ task: step.subtask ?? step.input ?? "" })) };
}

export function editedPlanSteps(steps: RunStep[], values: PlanFormValues): RunStep[] {
  return steps.map((step, index) => ({
    ...step,
    input: values.tasks[index].task,
    subtask: values.tasks[index].task,
  }));
}

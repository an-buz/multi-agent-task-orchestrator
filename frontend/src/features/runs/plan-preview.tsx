"use client";

import { useEffect, useMemo } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useWatch } from "react-hook-form";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { cancelRun, confirmRun, editRunPlan } from "./api";
import { runSteps } from "./model";
import { cacheRun, runQueryKey, runsQueryKey } from "./cache";
import {
  editedPlanSteps,
  planFormValues,
  planSchema,
  samePlanTasks,
  type PlanFormValues,
} from "./plan-schema";
import type { RunDetails } from "./types";

export function PlanPreview({ run }: { run: RunDetails }) {
  const client = useQueryClient();
  const steps = runSteps(run);
  const latestValues = useMemo(() => planFormValues(steps), [steps]);
  const form = useForm<PlanFormValues>({
    resolver: zodResolver(planSchema),
    defaultValues: latestValues,
  });
  const tasks = useWatch({ control: form.control, name: "tasks" });
  const reviewed = useWatch({ control: form.control, name: "expected_subtasks" });
  const changed = !samePlanTasks(reviewed, latestValues.expected_subtasks);
  const { isDirty } = form.formState;
  const { reset } = form;
  const mutation = useMutation({
    mutationFn: async (action: "confirm" | "cancel") => {
      if (action === "cancel") return cancelRun(run.id);
      const values = planSchema.parse(form.getValues());
      if (!samePlanTasks(values.expected_subtasks, latestValues.expected_subtasks)) {
        throw new Error("The plan changed. Reload the latest plan before starting.");
      }
      const saved = await editRunPlan(
        run.id,
        editedPlanSteps(steps, values),
        values.expected_subtasks,
      );
      reset(planFormValues(runSteps(saved)));
      await cacheRun(client, saved);
      return confirmRun(run.id, planFormValues(runSteps(saved)).expected_subtasks);
    },
    onError: () => client.invalidateQueries({ queryKey: runQueryKey(run.id), exact: true }),
    onSuccess: async (updated) => {
      await cacheRun(client, updated);
      await client.invalidateQueries({ queryKey: [...runsQueryKey, "list"] });
    },
  });
  const busy = mutation.isPending;
  useEffect(() => {
    if (changed && !isDirty && !busy) reset(latestValues);
  }, [changed, isDirty, busy, reset, latestValues]);
  return (
    <Dialog
      defaultOpen
      disablePointerDismissal={busy}
      onOpenChange={(open, details) => {
        if (!open && busy) details.cancel();
      }}
    >
      <DialogTrigger render={<Button variant="outline" />}>Review plan</DialogTrigger>
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] flex-col sm:max-w-3xl">
        <DialogHeader className="shrink-0 pr-8">
          <DialogTitle>Plan preview</DialogTitle>
          <DialogDescription>
            Review and edit the tasks before starting. Closing this window leaves the plan waiting
            for confirmation.
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex min-h-0 flex-col gap-6"
          onSubmit={form.handleSubmit(() => mutation.mutate("confirm"))}
        >
          <div className="min-h-0 overflow-y-auto">
            <FieldGroup>
              {steps.map((step, index) => (
                <Field
                  key={step.step_number}
                  data-invalid={Boolean(form.formState.errors.tasks?.[index])}
                >
                  <FieldLabel htmlFor={`plan-${run.id}-${step.step_number}`}>
                    {step.step_number}. {step.agent_name}
                  </FieldLabel>
                  <p className="text-xs text-muted-foreground">
                    Depends on: {step.depends_on.length ? step.depends_on.join(", ") : "none"}
                  </p>
                  <Textarea
                    id={`plan-${run.id}-${step.step_number}`}
                    aria-label={`Task for ${step.agent_name}`}
                    aria-invalid={Boolean(form.formState.errors.tasks?.[index])}
                    disabled={busy}
                    rows={3}
                    {...form.register(`tasks.${index}.task`)}
                  />
                  <FieldError errors={[form.formState.errors.tasks?.[index]?.task]} />
                </Field>
              ))}
            </FieldGroup>
          </div>
          <div className="flex shrink-0 flex-col gap-3">
            {changed && (
              <div role="alert" className="flex flex-col gap-2 text-sm">
                <p>
                  The plan changed in another session. Reload it before starting. Your unsaved edits
                  will be replaced.
                </p>
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy}
                  onClick={() => reset(latestValues)}
                >
                  Reload latest plan
                </Button>
              </div>
            )}
            {mutation.isError && (
              <p role="alert" className="text-destructive">
                {mutation.error.message}
              </p>
            )}
            <DialogFooter>
              <Button
                type="button"
                variant="secondary"
                disabled={busy}
                onClick={() => mutation.mutate("cancel")}
              >
                Cancel run
              </Button>
              <Button
                type="submit"
                disabled={
                  busy || changed || !tasks.length || tasks.some(({ task }) => !task.trim())
                }
              >
                {busy && mutation.variables === "confirm" ? "Starting…" : "Start run"}
              </Button>
            </DialogFooter>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

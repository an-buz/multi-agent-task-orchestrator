"use client";

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
import { cacheRun, runsQueryKey } from "./cache";
import { editedPlanSteps, planFormValues, planSchema, type PlanFormValues } from "./plan-schema";
import type { RunDetails } from "./types";

export function PlanPreview({ run }: { run: RunDetails }) {
  const client = useQueryClient();
  const steps = runSteps(run);
  const form = useForm<PlanFormValues>({
    resolver: zodResolver(planSchema),
    defaultValues: planFormValues(steps),
  });
  const tasks = useWatch({ control: form.control, name: "tasks" });
  const mutation = useMutation({
    mutationFn: async (action: "confirm" | "cancel") => {
      if (action === "cancel") return cancelRun(run.id);
      const values = planSchema.parse(form.getValues());
      await editRunPlan(run.id, editedPlanSteps(steps, values));
      return confirmRun(run.id);
    },
    onSuccess: async (updated) => {
      await cacheRun(client, updated);
      await client.invalidateQueries({ queryKey: [...runsQueryKey, "list"] });
    },
  });
  const busy = mutation.isPending;
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
                disabled={busy || !tasks.length || tasks.some(({ task }) => !task.trim())}
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

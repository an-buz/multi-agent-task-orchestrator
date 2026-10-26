"use client";

import Link from "next/link";
import { Controller, useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useAgents } from "@/features/agents/queries";
import { resolveRunDecision } from "./api";
import { cacheRun, runsQueryKey } from "./cache";
import { runSteps } from "./model";
import type { DecisionResolution, RunDecision, RunDetails } from "./types";

const assignmentSchema = z.object({
  agent_id: z.string().uuid("Choose an available agent."),
  task: z.string().trim().min(1, "Enter a fix task.").max(10000),
  comment: z.string().max(10000),
});

function PendingDecision({ run, decision }: { run: RunDetails; decision: RunDecision }) {
  const agents = useAgents();
  const client = useQueryClient();
  const form = useForm<z.infer<typeof assignmentSchema>>({
    resolver: zodResolver(assignmentSchema),
    defaultValues: {
      agent_id: decision.suggested_agent_id ?? "",
      task: decision.suggested_task,
      comment: "",
    },
  });
  const mutation = useMutation({
    mutationFn: (resolution: DecisionResolution) =>
      resolveRunDecision(run.id, decision.id, resolution),
    onSuccess: async (updated) => {
      await cacheRun(client, updated);
      await client.invalidateQueries({ queryKey: runsQueryKey });
    },
  });
  const available = (agents.data?.items ?? []).filter(
    (agent) => agent.available !== false && !agent.requires_reconfiguration,
  );
  const selected = useWatch({ control: form.control, name: "agent_id" });
  const paused = run.status === "PAUSED";
  const busy = mutation.isPending;
  const source = runSteps(run).find((step) => step.step_number === decision.source_step_number);
  return (
    <section
      aria-label={`Decision for step ${decision.source_step_number}`}
      className="flex flex-col gap-4 rounded-xl border border-border bg-card p-5"
    >
      <Alert>
        <AlertTitle>
          {source?.agent_name ?? "Agent"} found issues. Your decision is required.
        </AlertTitle>
        <AlertDescription>
          {paused
            ? "The workflow is paused until all pending decisions are resolved."
            : "Stopping the workflow. Active steps are finishing; no new steps will start."}
        </AlertDescription>
      </Alert>
      <ul className="flex flex-col gap-3">
        {decision.issues.map((issue, index) => (
          <li key={index} className="flex flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">{issue.severity}</Badge>
              <strong>{issue.title}</strong>
            </div>
            <p className="whitespace-pre-wrap text-sm text-muted-foreground">{issue.description}</p>
          </li>
        ))}
      </ul>
      <form
        onSubmit={form.handleSubmit((values) =>
          mutation.mutate({ action: "assign_fixes", ...values }),
        )}
        className="flex flex-col gap-4"
      >
        <FieldGroup>
          <Controller
            name="agent_id"
            control={form.control}
            render={({ field, fieldState }) => (
              <Field data-invalid={fieldState.invalid}>
                <FieldLabel htmlFor={`agent-${decision.id}`}>Agent to fix issues</FieldLabel>
                <Select
                  value={field.value || null}
                  onValueChange={(value) => field.onChange(value ?? "")}
                  disabled={busy || !paused}
                >
                  <SelectTrigger
                    id={`agent-${decision.id}`}
                    aria-invalid={fieldState.invalid}
                    onBlur={field.onBlur}
                  >
                    <SelectValue placeholder="Choose an available agent">
                      {available.find((agent) => agent.id === selected)?.name}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {available.map((agent) => (
                        <SelectItem key={agent.id} value={agent.id}>
                          {agent.name}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
                <FieldError errors={[fieldState.error]} />
              </Field>
            )}
          />
          <Field data-invalid={Boolean(form.formState.errors.task)}>
            <FieldLabel htmlFor={`task-${decision.id}`}>Fix task</FieldLabel>
            <Textarea
              id={`task-${decision.id}`}
              {...form.register("task")}
              aria-invalid={Boolean(form.formState.errors.task)}
              disabled={busy || !paused}
              rows={3}
            />
            <FieldError errors={[form.formState.errors.task]} />
          </Field>
          <Field data-invalid={Boolean(form.formState.errors.comment)}>
            <FieldLabel htmlFor={`comment-${decision.id}`}>Comment (optional)</FieldLabel>
            <Textarea
              id={`comment-${decision.id}`}
              {...form.register("comment")}
              maxLength={10000}
              disabled={busy}
              rows={2}
            />
            <FieldError errors={[form.formState.errors.comment]} />
          </Field>
        </FieldGroup>
        <p className="text-sm text-muted-foreground">
          Assigning fixes adds a correction step and a verification by the original agent before
          pending work continues. Previous results are preserved.
        </p>
        {agents.isError && (
          <p role="alert">
            Could not load agents. Retry by refreshing the page, or choose another action.
          </p>
        )}
        {paused && !agents.isPending && !available.length && (
          <p>
            No configured agents are available.{" "}
            <Link href="/agents" className="underline">
              Manage agents
            </Link>
            .
          </p>
        )}
        {mutation.isError && (
          <p role="alert" className="text-destructive">
            {mutation.error.message}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button
            type="submit"
            disabled={busy || !paused || !available.some((agent) => agent.id === selected)}
          >
            Assign fixes
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled={busy || !paused}
            onClick={() =>
              mutation.mutate({ action: "continue", comment: form.getValues("comment") })
            }
          >
            Continue without fixes
          </Button>
          <Button
            type="button"
            variant="destructive"
            disabled={busy}
            onClick={() =>
              mutation.mutate({ action: "cancel", comment: form.getValues("comment") })
            }
          >
            Cancel run
          </Button>
        </div>
      </form>
    </section>
  );
}

export function RunDecisions({ run }: { run: RunDetails }) {
  const pending = (run.decisions ?? []).filter((decision) => decision.status === "PENDING");
  const resolved = (run.decisions ?? []).filter((decision) => decision.status === "RESOLVED");
  const modelBlocked =
    run.pause_reasons?.includes("MODEL_UNAVAILABLE") ||
    (run.status === "PAUSED" && !pending.length && !run.pause_reasons?.length);
  return (
    <div className="flex flex-col gap-4">
      {modelBlocked && (
        <Alert>
          <AlertTitle>Waiting for agent reconfiguration</AlertTitle>
          <AlertDescription>
            Save unavailable agents with an enabled model to resume when all blockers are cleared.
            Completed steps are preserved. <Link href="/agents">Manage agents</Link>.
          </AlertDescription>
        </Alert>
      )}
      {pending.length > 0 && (
        <Dialog key={`${run.id}-${pending.map((decision) => decision.id).join("-")}`} defaultOpen>
          <DialogTrigger render={<Button variant="outline" className="self-start" />}>
            Review decisions ({pending.length})
          </DialogTrigger>
          <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-2xl">
            <DialogHeader className="pr-8">
              <DialogTitle>Your decision is required</DialogTitle>
              <DialogDescription>
                Review the agent findings and choose how to proceed. Closing this window keeps the
                workflow waiting for your decision.
              </DialogDescription>
            </DialogHeader>
            {pending.map((decision) => (
              <PendingDecision key={`${run.id}-${decision.id}`} run={run} decision={decision} />
            ))}
          </DialogContent>
        </Dialog>
      )}
      {resolved.length > 0 && (
        <details className="rounded-xl border border-border bg-card p-4">
          <summary className="cursor-pointer text-sm font-medium">
            Decision history ({resolved.length})
          </summary>
          <ul className="mt-3 flex flex-col gap-3">
            {resolved.map((decision) => (
              <li key={decision.id} className="text-sm">
                <p>
                  Step {decision.source_step_number}:{" "}
                  {decision.issues.map((issue) => issue.title).join(", ")}
                </p>
                <p className="text-muted-foreground">
                  {decision.resolution?.action === "assign_fixes"
                    ? `Fixes assigned; new steps ${decision.followup_step_numbers.join(", ")}`
                    : decision.resolution?.action === "continue"
                      ? "Continued without fixes"
                      : "Run cancelled"}
                </p>
                {decision.resolution?.task && (
                  <p className="whitespace-pre-wrap">{decision.resolution.task}</p>
                )}
                {decision.resolution?.comment && (
                  <p className="whitespace-pre-wrap">{decision.resolution.comment}</p>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

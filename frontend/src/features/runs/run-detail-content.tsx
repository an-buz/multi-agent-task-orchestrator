"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useQueryClient } from "@tanstack/react-query";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Textarea } from "@/components/ui/textarea";
import type { RunStep } from "@/features/runs/types";
import { contextFileDownloadUrl } from "@/features/files/queries";
import { cancelRun, confirmRun, editRunPlan, exportRun, retryRunStep } from "@/features/runs/api";

import { useRun, runsQueryKey } from "./queries";
import { useRunEvents } from "./use-run-events";
import { canRetryStep, runSteps as getRunSteps } from "./model";
import { StatusBadge } from "@/components/status-badge";

export default function RunDetailContent({ id }: { id: string }) {
  const client = useQueryClient();
  const query = useRun(id);
  const { activityEvents: events, connectionError: streamError } = useRunEvents(id);
  const [actionError, setActionError] = useState("");
  const [pending, setPending] = useState(false);
  const [planDraft, setPlanDraft] = useState<RunStep[] | null>(null);
  async function perform(action: () => Promise<unknown>, refresh = true) {
    setPending(true);
    setActionError("");
    try {
      await action();
      if (refresh) {
        setPlanDraft(null);
        await client.invalidateQueries({ queryKey: runsQueryKey });
      }
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Could not complete this action.");
    } finally {
      setPending(false);
    }
  }
  async function download(format: "json" | "md" | "pdf") {
    const response = await exportRun(id, format);
    if (!response.ok) throw new Error(`Export failed (${response.status})`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `run-${id}.${format}`;
    link.click();
    URL.revokeObjectURL(url);
  }
  const run = query.data;
  const runSteps = getRunSteps(run);
  return (
    <AppShell>
      <section className="min-w-0">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-6 py-5 lg:px-8">
          <div>
            <h1 className="text-xl font-semibold">Run details</h1>
            <p className="mt-1 font-mono text-xs text-muted-foreground">{id}</p>
          </div>
          {run && (
            <div className="flex gap-2">
              <StatusBadge status={run.status} />
              {["PLANNING", "AWAITING_CONFIRMATION", "IN_PROGRESS", "PAUSED"].includes(
                run.status,
              ) && (
                <Button
                  variant="secondary"
                  disabled={pending}
                  onClick={() => void perform(() => cancelRun(id))}
                >
                  Cancel run
                </Button>
              )}
            </div>
          )}
        </header>
        <div className="space-y-5 p-6 lg:p-8">
          {actionError && (
            <p role="alert" className="text-destructive">
              {actionError}
            </p>
          )}
          {query.isLoading && <p>Loading run…</p>}
          {query.isError && (
            <p role="alert" className="text-destructive">
              Could not load this run.
            </p>
          )}
          {run && (
            <>
              {run.status === "PAUSED" && (
                <Alert>
                  <AlertTitle>Waiting for agent reconfiguration</AlertTitle>
                  <AlertDescription>
                    Save unavailable agents with an enabled model to resume this run automatically.
                    Completed steps are preserved. <Link href="/agents">Manage agents</Link>.
                  </AlertDescription>
                </Alert>
              )}
              <section className="rounded-xl border border-border bg-card p-5">
                <h2 className="text-sm font-semibold">Task</h2>
                <p className="mt-2 whitespace-pre-wrap text-sm text-foreground">{run.task}</p>
                {(run.files?.length ?? 0) > 0 && (
                  <div className="mt-3 flex flex-col gap-2" aria-label="Context attachments">
                    <h3 className="text-sm font-medium">Context attachments</h3>
                    {run.files?.map((file) => (
                      <a
                        key={file.id}
                        href={contextFileDownloadUrl(file.id)}
                        className="text-sm text-primary underline"
                      >
                        Download {file.filename} ({file.size_bytes} bytes)
                      </a>
                    ))}
                  </div>
                )}
                {run.context_text && (
                  <pre className="mt-3 overflow-auto rounded bg-background p-3 text-xs text-muted-foreground">
                    {run.context_text}
                  </pre>
                )}
              </section>
              {run.status === "AWAITING_CONFIRMATION" && (
                <section
                  aria-label="Plan preview"
                  className="flex flex-col gap-3 rounded-xl border border-border p-5"
                >
                  <h2 className="text-sm font-semibold">Plan preview</h2>
                  {(planDraft ?? runSteps).map((step) => (
                    <label key={step.step_number} className="flex flex-col gap-2">
                      {step.step_number}. {step.agent_name}
                      <Textarea
                        aria-label={`Task for ${step.agent_name}`}
                        disabled={pending}
                        value={step.subtask ?? step.input ?? ""}
                        onChange={(event) =>
                          setPlanDraft(
                            (planDraft ?? runSteps).map((item) =>
                              item.step_number === step.step_number
                                ? { ...item, subtask: event.target.value }
                                : item,
                            ),
                          )
                        }
                      />
                    </label>
                  ))}
                  <Button
                    disabled={
                      pending ||
                      (planDraft ?? runSteps).some(
                        (step) => !(step.subtask ?? step.input ?? "").trim(),
                      )
                    }
                    onClick={() =>
                      void perform(async () => {
                        if (planDraft) await editRunPlan(id, planDraft);
                        await confirmRun(id);
                      })
                    }
                  >
                    Confirm and run
                  </Button>
                </section>
              )}
              <section className="rounded-xl border border-border bg-card p-5">
                <h2 className="mb-3 text-sm font-semibold">Execution steps</h2>
                <div className="space-y-3">
                  {runSteps.map((step) => (
                    <article key={step.step_number} className="rounded-lg border border-border p-4">
                      <div className="flex flex-wrap justify-between gap-2">
                        <h3 className="text-sm font-medium">
                          {step.step_number}. {step.agent_name}
                        </h3>
                        <StatusBadge status={step.status} />
                      </div>
                      {step.input && (
                        <p className="mt-2 text-xs text-muted-foreground">Input: {step.input}</p>
                      )}
                      {step.output && (
                        <p
                          aria-label={`Output for step ${step.step_number}`}
                          className="mt-2 whitespace-pre-wrap text-sm text-foreground"
                        >
                          {step.output}
                        </p>
                      )}
                      {step.status === "IN_PROGRESS" && (
                        <p role="status" className="mt-2 text-xs text-muted-foreground">
                          Generating response…
                        </p>
                      )}
                      {step.error && (
                        <p role="alert" className="mt-2 text-xs text-destructive">
                          {step.error.message}
                        </p>
                      )}
                      {canRetryStep(run, step) && (
                        <button
                          className="mt-3 text-xs text-status-completed underline"
                          disabled={pending}
                          onClick={() => void perform(() => retryRunStep(id, step.step_number))}
                        >
                          Retry step
                        </button>
                      )}
                    </article>
                  ))}
                </div>
              </section>
              {run.final_report && (
                <section className="prose dark:prose-invert max-w-none rounded-xl border border-border bg-card p-5">
                  <h2>Final report</h2>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{run.final_report}</ReactMarkdown>
                </section>
              )}
              <section className="rounded-xl border border-border bg-background p-5">
                <h2 className="text-sm font-semibold">Live events</h2>
                {streamError && (
                  <p role="status" className="mt-2 text-xs text-status-warning">
                    Connection lost. Reconnecting…
                  </p>
                )}
                <div
                  aria-live="polite"
                  className="mt-3 max-h-56 space-y-1 overflow-auto font-mono text-xs text-muted-foreground"
                >
                  {events
                    .filter((event) => event.event !== "agent:stream_chunk")
                    .map((event, i) => (
                      <p key={event.id ?? i}>
                        {event.ts ?? event.timestamp} {event.event}
                      </p>
                    ))}
                </div>
              </section>
              {run.final_report && (
                <div className="flex flex-wrap gap-2">
                  {(["json", "md", "pdf"] as const).map((format) => (
                    <button
                      key={format}
                      className="rounded border border-border px-3 py-2 text-xs uppercase"
                      disabled={pending}
                      onClick={() => void perform(() => download(format), false)}
                    >
                      {format === "md"
                        ? "Download MD"
                        : format === "pdf"
                          ? "Download PDF"
                          : "Download JSON"}
                    </button>
                  ))}
                  <button
                    className="rounded border border-border px-3 py-2 text-xs"
                    disabled={pending}
                    onClick={() =>
                      void perform(
                        () => navigator.clipboard.writeText(run.final_report ?? ""),
                        false,
                      )
                    }
                  >
                    Copy Markdown
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </section>
    </AppShell>
  );
}

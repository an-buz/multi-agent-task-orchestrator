"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  Bot,
  CircleHelp,
  LockKeyhole,
  MoreHorizontal,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/status-badge";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import type { RunDetails, RunSummary, RunEvent, RunStep } from "@/features/runs/types";
import { eventKey, runSteps } from "@/features/runs/model";
import { consoleEvents, eventPresentation } from "./console-events";
import { cn } from "@/lib/utils";

const statusLabels = {
  PENDING: "Pending",
  PLANNING: "Planning",
  AWAITING_CONFIRMATION: "Awaiting confirmation",
  IN_PROGRESS: "In Progress",
  PAUSED: "Paused",
  COMPLETED: "Completed",
  FAILED: "Failed",
  CANCELLED: "Cancelled",
};

export function RunPipeline({
  run,
  runs,
  selectRun,
  step,
  selectStep,
  pending,
  failed,
}: {
  run?: RunDetails;
  runs: RunSummary[];
  selectRun: (id: string) => void;
  step?: RunStep;
  selectStep: (number: number) => void;
  pending?: boolean;
  failed?: boolean;
}) {
  const [options, setOptions] = useState(false);
  const router = useRouter();
  const steps = runSteps(run);
  const choices = run && !runs.some((item) => item.id === run.id) ? [run, ...runs] : runs;
  return (
    <section
      aria-label="Execution pipeline"
      className="rounded-xl border border-border bg-card p-4 lg:p-5"
    >
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Active execution pipeline
          </h2>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {run?.workflow_title ?? "No run selected"}
          </p>
        </div>
        <Button
          aria-label="More pipeline options"
          variant="ghost"
          className="[&_svg]:size-4.5 [&_svg]:text-muted-foreground hover:[&_svg]:text-foreground"
          aria-expanded={options}
          onClick={() => setOptions(!options)}
        >
          <MoreHorizontal size={18} />
        </Button>
      </div>
      {options && (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <Select
            value={run?.id ?? null}
            onValueChange={(value) => {
              if (value) selectRun(value);
            }}
          >
            <SelectTrigger aria-label="Monitored run" className="max-w-64">
              {run ? `${run.workflow_title ?? "Run"} · ${run.id.slice(0, 8)}` : "Choose run"}
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {choices.map((item) => (
                  <SelectItem key={item.id} value={item.id}>
                    {item.workflow_title ?? "Run"} · {item.id.slice(0, 8)} · {item.status}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
          <Button variant="secondary" onClick={() => router.push("/workflows")}>
            Manage workflows
          </Button>
          <Button variant="secondary" onClick={() => router.push("/runs")}>
            View run history
          </Button>
          {run && (
            <>
              <Button variant="secondary" onClick={() => router.push(`/runs/${run.id}`)}>
                Open run details
              </Button>
              <p
                aria-label="Monitored task"
                className="w-full whitespace-pre-wrap text-xs text-muted-foreground"
              >
                {run.task}
              </p>
            </>
          )}
        </div>
      )}
      {!run && !pending && !failed && (
        <p className="text-sm text-muted-foreground">
          No runs yet. Start a workflow to monitor its execution.
        </p>
      )}
      {run?.status === "PLANNING" && (
        <p role="status" className="text-sm text-muted-foreground">
          Planning the execution…
        </p>
      )}
      {run?.status === "AWAITING_CONFIRMATION" && (
        <p className="mb-3 text-sm text-muted-foreground">
          The plan awaits confirmation. Open Run details to review and confirm it.
        </p>
      )}
      {run?.planning_error && (
        <p role="alert" className="text-sm text-destructive">
          {run.planning_error.message}
        </p>
      )}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {steps.map((item, index) => (
          <div key={item.step_number} className="flex min-w-30.5 flex-1 items-center gap-2">
            <article
              className={`min-w-29.5 flex-1 rounded-lg border p-3 ${item.status === "IN_PROGRESS" ? "border-status-progress bg-status-progress/10" : "border-border bg-card"}`}
            >
              <button
                aria-label={`Inspect step ${item.step_number}: ${item.agent_name}`}
                aria-pressed={step?.step_number === item.step_number}
                className="block w-full text-left outline-none focus-visible:ring-1 focus-visible:ring-ring"
                onClick={() => selectStep(item.step_number)}
              >
                <h3 className="truncate text-xs font-semibold text-foreground">
                  {item.agent_name}
                </h3>
                <p className="mt-1 truncate font-mono text-[10px] text-muted-foreground">
                  {item.model ?? "Model unavailable"}
                </p>
                <StatusBadge status={item.status} variant="pipeline" />
              </button>
            </article>
            {index < steps.length - 1 && (
              <ArrowRight aria-hidden="true" className="shrink-0 text-muted-foreground" size={15} />
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

export function RunConsole({
  runId,
  events,
  connectionError,
  steps,
}: {
  runId?: string;
  events: RunEvent[];
  connectionError: boolean;
  steps: RunStep[];
}) {
  const [hidden, setHidden] = useState<{ runId?: string; keys: Set<string> }>({ keys: new Set() });
  const scrollRef = useRef<HTMLDivElement>(null);
  const visible = consoleEvents(events).filter(
    (event) => hidden.runId !== runId || !hidden.keys.has(eventKey(event)),
  );
  const latestEvent = visible.at(-1);

  useEffect(() => {
    const viewport = scrollRef.current;
    if (viewport) viewport.scrollTop = viewport.scrollHeight;
  }, [latestEvent, runId]);

  return (
    <section className="flex min-h-97.5 flex-col overflow-hidden rounded-xl border border-border bg-background">
      <div className="flex items-center justify-between border-b border-border bg-card px-4 py-3">
        <h2 className="flex items-center gap-2 font-mono text-xs font-semibold tracking-wide text-foreground">
          <i className="size-2 rounded-full bg-status-completed" />
          LIVE ORCHESTRATION CONSOLE
        </h2>
        <Button
          variant="ghost"
          disabled={!visible.length}
          onClick={() => setHidden({ runId, keys: new Set(events.map(eventKey)) })}
        >
          Clear
        </Button>
      </div>
      <div
        ref={scrollRef}
        aria-label="Run orchestration events"
        className="dashboard-console-scroll flex h-91 flex-col gap-3 overflow-auto p-4 font-mono text-[11px] leading-5"
      >
        {!visible.length && (
          <p className="text-muted-foreground">
            {hidden.runId === runId && hidden.keys.size
              ? "Console cleared. Waiting for new events."
              : "No events yet."}
          </p>
        )}
        {visible.map((event) => {
          const { tag, tone, message } = eventPresentation(event, steps);
          return (
            <div
              key={eventKey(event)}
              className="flex min-w-max shrink-0 items-center gap-3 whitespace-nowrap"
            >
              <time className="w-20 shrink-0 text-muted-foreground">
                {event.ts || event.timestamp
                  ? new Date(event.ts ?? event.timestamp!).toLocaleTimeString()
                  : "—"}
              </time>
              <span
                title={tag}
                aria-label={event.event}
                className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] leading-4 ${tone === "cyan" ? "bg-status-progress/15 text-status-progress" : tone === "violet" ? "bg-status-highlight/20 text-status-highlight" : "bg-status-completed/15 text-status-completed"}`}
              >
                {tag}
              </span>
              <span className="text-foreground">{message}</span>
            </div>
          );
        })}
        <p className="mt-5 flex items-center gap-2 text-status-completed">
          <ArrowDownToLine size={14} />
          {connectionError
            ? "Reconnecting to live events. Run state continues updating by polling."
            : runId
              ? "Following run events…"
              : "Waiting for a run."}
        </p>
      </div>
    </section>
  );
}

export function RunInspector({ run, step }: { run?: RunDetails; step?: RunStep }) {
  const [help, setHelp] = useState(false);
  const tone =
    step?.status === "COMPLETED"
      ? "text-status-completed"
      : step?.status === "FAILED"
        ? "text-destructive"
        : step?.status === "IN_PROGRESS" || step?.status === "PLANNING"
          ? "text-status-warning"
          : "text-muted-foreground";
  const prompt = step?.prompt_tokens ?? 0,
    completion = step?.completion_tokens ?? 0;
  const steps = runSteps(run),
    tokens = prompt + completion;
  const completed = steps.filter((item) => item.status === "COMPLETED").length;
  const progress = steps.length ? Math.round((completed / steps.length) * 100) : 0;
  return (
    <aside
      aria-label="Agent inspector"
      className="flex flex-col gap-3 border-t border-border bg-background p-4 xl:border-l xl:border-t-0"
    >
      <h2 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        Active agent inspector
      </h2>
      <section
        className={cn("flex items-center gap-3 rounded-lg border border-border bg-card p-3", tone)}
      >
        <span className="grid size-10 shrink-0 place-items-center rounded-full border border-current bg-current/70">
          <Bot size={20} />
        </span>
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-foreground">
            {step?.agent_name ?? "No agent selected"}
          </h3>
          <p className="truncate font-mono text-[10px]">{step?.model ?? "Model unavailable"}</p>
        </div>
      </section>
      <section className={cn("py-1", tone)}>
        <div className="mb-2 flex justify-between text-xs">
          <span>{step ? statusLabels[step.status] : "Waiting for a run"}</span>
          <span className="font-mono">{progress}%</span>
        </div>
        <div
          role="progressbar"
          aria-label="Completed steps"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={progress}
          className="h-1.5 overflow-hidden rounded-full bg-secondary"
        >
          <div className="h-full bg-current" style={{ width: `${progress}%` }} />
        </div>
      </section>
      <section className="rounded-lg border border-border bg-card p-3">
        <h3 className="mb-2 text-[10px] font-semibold uppercase text-muted-foreground">
          Current step
        </h3>
        {step?.status === "IN_PROGRESS" && (
          <p role="status" className="mb-2 text-xs text-muted-foreground">
            {step.output ? "Receiving model response…" : "Waiting for model response…"}
          </p>
        )}
        <p
          aria-label={step ? `Output for step ${step.step_number}` : undefined}
          className="dashboard-inspector-scroll h-[50.4px] overflow-auto whitespace-pre-wrap warp-break-words font-mono text-xs leading-[1.4] text-foreground"
        >
          {step?.output ??
            step?.subtask ??
            "Select a run with execution steps to inspect an agent."}
        </p>
        {step?.error && (
          <p role="alert" className="mt-2 text-xs text-destructive">
            {step.error.message}
          </p>
        )}
      </section>
      <section className="rounded-lg border border-border bg-card p-3">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-[10px] font-semibold uppercase text-muted-foreground">
            Input context
          </h3>
          <Button
            aria-label="Help about input context"
            variant="ghost"
            aria-expanded={help}
            onClick={() => setHelp(!help)}
          >
            <CircleHelp size={13} />
          </Button>
        </div>
        {help && (
          <div className="mb-2 text-xs text-muted-foreground">
            <p>
              Input context contains the task and supporting information passed to this step.
              Current step displays live output when available.
            </p>
            {step && (
              <p className="mt-2">
                Step {step.step_number} · Attempt {step.attempt ?? 0} ·{" "}
                {((step.duration_ms ?? 0) / 1000).toFixed(2)} s
              </p>
            )}
            {run && (
              <p className="mt-2">
                Run totals: {run.total_tokens.toLocaleString()} tokens ·{" "}
                {((run.total_time_ms ?? 0) / 1000).toFixed(2)} s
              </p>
            )}
          </div>
        )}
        <pre className="dashboard-inspector-scroll h-29 overflow-auto rounded bg-background p-2.5 font-mono text-[10px] leading-4 text-status-progress">
          {step?.input ?? "Input will be prepared when the step starts."}
        </pre>
      </section>
      <section className="rounded-lg border border-border bg-card p-3">
        <div className="flex items-center justify-between">
          <h3 className="text-[10px] font-semibold uppercase text-muted-foreground">Token usage</h3>
          <span aria-label="Step tokens" className="font-mono text-[11px] text-foreground">
            {tokens.toLocaleString()} tokens
          </span>
        </div>
        <div
          aria-label="Step token distribution"
          className="mt-2 flex h-2 overflow-hidden rounded-full bg-secondary"
        >
          <span
            className="bg-status-highlight"
            style={{ width: `${tokens ? (prompt / tokens) * 100 : 0}%` }}
          />
          <span
            className="bg-status-progress"
            style={{ width: `${tokens ? (completion / tokens) * 100 : 0}%` }}
          />
        </div>
        <div className="mt-2 flex gap-3 text-[10px] text-muted-foreground">
          <span className="text-status-highlight">● Prompt ({prompt.toLocaleString()})</span>
          <span className="text-status-progress">● Completion ({completion.toLocaleString()})</span>
        </div>
      </section>
      <section className="mt-auto rounded-lg border border-border bg-card p-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold">Final report</h3>
          {!run?.final_report && <LockKeyhole size={14} className="text-muted-foreground" />}
        </div>
        {run?.final_report ? (
          <div className="dashboard-inspector-scroll prose mt-2 h-15 max-w-none overflow-auto text-xs prose-headings:text-foreground prose-p:text-foreground prose-strong:text-foreground prose-code:text-foreground">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{run.final_report}</ReactMarkdown>
          </div>
        ) : (
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            The workflow summary artifact will be generated automatically once the run completes.
          </p>
        )}
      </section>
      <p className="flex items-center justify-center gap-1 text-[10px] text-muted-foreground">
        <Activity size={12} />
        {run ? "Persisted run data · live updates" : "Waiting for a run"}
      </p>
    </aside>
  );
}

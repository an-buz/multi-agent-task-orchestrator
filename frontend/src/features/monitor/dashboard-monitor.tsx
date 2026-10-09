"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Activity, ArrowDownToLine, ArrowRight, Bot, CircleHelp, LockKeyhole, MoreHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/status-badge";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger } from "@/components/ui/select";
import type { RunDetails, RunEvent, RunStep } from "@/features/runs/types";
import { eventKey, runSteps } from "./use-run-monitor";

const statusLabels = {
  PENDING: "Pending", PLANNING: "Planning", AWAITING_CONFIRMATION: "Awaiting confirmation",
  IN_PROGRESS: "In Progress", COMPLETED: "Completed", FAILED: "Failed", CANCELLED: "Cancelled",
};

function eventPresentation(event: RunEvent, steps: RunStep[]) {
  const data = event.data ?? event.payload ?? {};
  const agent = steps.find((step) => step.step_number === data.stepNumber)?.agent_name;
  const tool = event.event.includes("tool");
  const tone = tool ? "cyan" : event.event.startsWith("agent:") && !event.event.endsWith("completed") ? "violet" : "emerald";
  const tag = tool ? `Tool: ${typeof data.toolName === "string" ? data.toolName : "Call"}`
    : tone === "violet" ? `Agent: ${agent ?? "Update"}` : `Status: ${event.event.split(":").at(-1)?.replaceAll("_", " ")}`;
  let message: string;
  if (typeof data.summary === "string") message = data.summary;
  else if (event.event === "agent:stream_chunk") message = data.reset ? "Starting a new response."
    : typeof data.textDelta === "string" ? data.textDelta : "Response updated.";
  else if (event.event === "run:snapshot") message = "Persisted run state restored.";
  else if (event.event === "plan:ready") message = "Execution plan prepared and awaiting confirmation.";
  else if (event.event === "task:started") message = "Workflow execution started.";
  else if (event.event === "task:finished") message = `Workflow completed${typeof data.totalTokens === "number" ? ` · ${data.totalTokens.toLocaleString()} tokens` : ""}.`;
  else if (event.event === "agent:status_change" && typeof data.status === "string") message = `${agent ?? "Agent"}: ${data.status.toLowerCase().replaceAll("_", " ")}.`;
  else if (event.event === "agent:completed") message = `${agent ?? "Agent"} completed the step.`;
  else message = JSON.stringify(data);
  return { tag, tone, message };
}

export function RunPipeline({ run, runs, selectRun, step, selectStep, pending, failed }: {
  run?: RunDetails; runs: RunDetails[]; selectRun: (id: string) => void;
  step?: RunStep; selectStep: (number: number) => void;
  pending?: boolean; failed?: boolean;
}) {
  const [options, setOptions] = useState(false);
  const router = useRouter();
  const steps = runSteps(run);
  const choices = run && !runs.some((item) => item.id === run.id) ? [run, ...runs] : runs;
  return <section aria-label="Execution pipeline" className="rounded-xl border border-(--border) bg-(--surface) p-4 lg:p-5">
    <div className="mb-4 flex items-center justify-between">
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Active execution pipeline</h2>
        <p className="mt-1 text-[11px] text-slate-600">{run?.workflow_title ?? "No run selected"}</p>
      </div>
      <Button aria-label="More pipeline options" variant="ghost"
        className="[&_svg]:size-4.5 [&_svg]:text-slate-500 hover:[&_svg]:text-slate-300"
        aria-expanded={options} onClick={() => setOptions(!options)}><MoreHorizontal size={18} /></Button>
    </div>
    {options && <div className="mb-4 flex flex-wrap items-center gap-2">
      <Select value={run?.id ?? null} onValueChange={(value) => { if (value) selectRun(value); }}>
        <SelectTrigger aria-label="Monitored run" className="max-w-64">
          {run ? `${run.workflow_title ?? "Run"} · ${run.id.slice(0, 8)}` : "Choose run"}
        </SelectTrigger><SelectContent><SelectGroup>
          {choices.map((item) => <SelectItem key={item.id} value={item.id}>
            {item.workflow_title ?? "Run"} · {item.id.slice(0, 8)} · {item.status}
          </SelectItem>)}
        </SelectGroup></SelectContent>
      </Select>
      <Button variant="secondary" onClick={() => router.push("/workflows")}>Manage workflows</Button>
      <Button variant="secondary" onClick={() => router.push("/runs")}>View run history</Button>
      {run && <>
        <Button variant="secondary" onClick={() => router.push(`/runs/${run.id}`)}>Open run details</Button>
        <p aria-label="Monitored task" className="w-full whitespace-pre-wrap text-xs text-slate-400">{run.task}</p>
      </>}
    </div>}
    {!run && !pending && !failed && <p className="text-sm text-muted-foreground">No runs yet. Start a workflow to monitor its execution.</p>}
    {run?.status === "PLANNING" && <p role="status" className="text-sm text-muted-foreground">Planning the execution…</p>}
    {run?.status === "AWAITING_CONFIRMATION" && <p className="mb-3 text-sm text-muted-foreground">The plan awaits confirmation. Open Run details to review and confirm it.</p>}
    {run?.planning_error && <p role="alert" className="text-sm text-destructive">{run.planning_error.message}</p>}
    <div className="flex gap-2 overflow-x-auto pb-1">
      {steps.map((item, index) => <div key={item.step_number} className="flex min-w-30.5 flex-1 items-center gap-2">
        <article className={`min-w-29.5 flex-1 rounded-lg border p-3 ${item.status === "IN_PROGRESS" ? "border-blue-500 bg-blue-500/10" : "border-(--border) bg-[#0b1220]"}`}>
          <button aria-label={`Inspect step ${item.step_number}: ${item.agent_name}`} aria-pressed={step?.step_number === item.step_number}
            className="block w-full text-left outline-none focus-visible:ring-1 focus-visible:ring-ring" onClick={() => selectStep(item.step_number)}>
            <h3 className="truncate text-xs font-semibold text-slate-200">{item.agent_name}</h3>
            <p className="mt-1 truncate font-mono text-[10px] text-slate-500">{item.model ?? "Model unavailable"}</p>
            <StatusBadge status={item.status} variant="pipeline" />
          </button>
        </article>
        {index < steps.length - 1 && <ArrowRight aria-hidden="true" className="shrink-0 text-slate-700" size={15} />}
      </div>)}
    </div>
  </section>;
}

export function RunConsole({ runId, events, connectionError, steps }: {
  runId?: string; events: RunEvent[]; connectionError: boolean; steps: RunStep[];
}) {
  const [hidden, setHidden] = useState<{ runId?: string; keys: Set<string> }>({ keys: new Set() });
  const visible = events.filter((event) => hidden.runId !== runId || !hidden.keys.has(eventKey(event)));
  return <section className="flex min-h-97.5 flex-col overflow-hidden rounded-xl border border-(--border) bg-[#050816]">
    <div className="flex items-center justify-between border-b border-(--border) bg-(--surface) px-4 py-3">
      <h2 className="flex items-center gap-2 font-mono text-xs font-semibold tracking-wide text-slate-200">
        <i className="size-2 rounded-full bg-emerald-400" />LIVE ORCHESTRATION CONSOLE
      </h2>
      <Button variant="ghost" disabled={!visible.length} onClick={() => setHidden({ runId, keys: new Set(events.map(eventKey)) })}>Clear</Button>
    </div>
    <div aria-label="Run orchestration events" className="dashboard-console-scroll h-[364px] space-y-3 overflow-auto p-4 font-mono text-[11px] leading-5">
      {!visible.length && <p className="text-slate-500">{hidden.runId === runId && hidden.keys.size ? "Console cleared. Waiting for new events." : "No events yet."}</p>}
      {visible.map((event) => {
        const { tag, tone, message } = eventPresentation(event, steps);
        return <div key={eventKey(event)} className="grid grid-cols-[58px_98px_minmax(0,1fr)] gap-2">
          <time className="text-slate-600">{event.ts || event.timestamp ? new Date(event.ts ?? event.timestamp!).toLocaleTimeString() : "—"}</time>
          <span title={event.event} aria-label={event.event}
            className={`w-fit self-start rounded px-1.5 py-0.5 text-[10px] leading-4 ${tone === "cyan" ? "bg-cyan-500/15 text-cyan-300" : tone === "violet" ? "bg-violet-500/20 text-violet-300" : "bg-emerald-500/15 text-emerald-300"}`}>{tag}</span>
          <span className="min-w-0 whitespace-pre-wrap break-words text-slate-300">{message}</span>
        </div>;
      })}
      <p className="mt-5 flex items-center gap-2 text-emerald-400"><ArrowDownToLine size={14} />
        {connectionError ? "Reconnecting to live events. Run state continues updating by polling." : runId ? "Following run events…" : "Waiting for a run."}
      </p>
    </div>
  </section>;
}

export function RunInspector({ run, step }: { run?: RunDetails; step?: RunStep }) {
  const [help, setHelp] = useState(false);
  const prompt = step?.prompt_tokens ?? 0, completion = step?.completion_tokens ?? 0;
  const steps = runSteps(run), tokens = prompt + completion;
  const completed = steps.filter((item) => item.status === "COMPLETED").length;
  const progress = steps.length ? Math.round(completed / steps.length * 100) : 0;
  return <aside aria-label="Agent inspector" className="flex flex-col gap-3 border-t border-(--border) bg-[#080e1d] p-4 xl:border-l xl:border-t-0">
    <h2 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Active agent inspector</h2>
    <section className="flex items-center gap-3 rounded-lg border border-(--border) bg-(--surface) p-3">
      <span className="grid size-10 shrink-0 place-items-center rounded-full border border-amber-500 bg-amber-950/70 text-amber-400"><Bot size={20} /></span>
      <div className="min-w-0"><h3 className="text-sm font-semibold">{step?.agent_name ?? "No agent selected"}</h3>
        <p className="truncate font-mono text-[10px] text-amber-400">{step?.model ?? "Model unavailable"}</p>
      </div>
    </section>
    <section className="py-1">
      <div className="mb-2 flex justify-between text-xs"><span className="text-slate-400">{step ? statusLabels[step.status] : "Waiting for a run"}</span><span className="font-mono text-amber-300">{progress}%</span></div>
      <div role="progressbar" aria-label="Completed steps" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress} className="h-1.5 overflow-hidden rounded-full bg-slate-800"><div className="h-full bg-amber-400" style={{ width: `${progress}%` }} /></div>
    </section>
    <section className="rounded-lg border border-(--border) bg-(--surface) p-3">
      <h3 className="mb-2 text-[10px] font-semibold uppercase text-slate-400">Current step</h3>
      <p aria-label={step ? `Output for step ${step.step_number}` : undefined}
        className="dashboard-inspector-scroll h-[50.4px] overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-[1.4] text-slate-300">{step?.output ?? step?.subtask ?? "Select a run with execution steps to inspect an agent."}</p>
      {step?.error && <p role="alert" className="mt-2 text-xs text-rose-300">{step.error.message}</p>}
    </section>
    <section className="rounded-lg border border-(--border) bg-(--surface) p-3">
      <div className="mb-2 flex items-center justify-between"><h3 className="text-[10px] font-semibold uppercase text-slate-400">Input context</h3>
        <Button aria-label="Help about input context" variant="ghost" aria-expanded={help} onClick={() => setHelp(!help)}><CircleHelp size={13} /></Button>
      </div>
      {help && <div className="mb-2 text-xs text-muted-foreground">
        <p>Input context contains the task and supporting information passed to this step. Current step displays live output when available.</p>
        {step && <p className="mt-2">Step {step.step_number} · Attempt {step.attempt ?? 0} · {((step.duration_ms ?? 0) / 1000).toFixed(2)} s</p>}
        {run && <p className="mt-2">Run totals: {run.total_tokens.toLocaleString()} tokens · {((run.total_time_ms ?? 0) / 1000).toFixed(2)} s</p>}
      </div>}
      <pre className="dashboard-inspector-scroll h-29 overflow-auto rounded bg-[#050816] p-2.5 font-mono text-[10px] leading-4 text-cyan-300">{step?.input ?? "Input will be prepared when the step starts."}</pre>
    </section>
    <section className="rounded-lg border border-(--border) bg-(--surface) p-3">
      <div className="flex items-center justify-between"><h3 className="text-[10px] font-semibold uppercase text-slate-400">Token usage</h3><span aria-label="Step tokens" className="font-mono text-[11px] text-slate-300">{tokens.toLocaleString()} tokens</span></div>
      <div aria-label="Step token distribution" className="mt-2 flex h-2 overflow-hidden rounded-full bg-slate-800"><span className="bg-violet-400" style={{ width: `${tokens ? prompt / tokens * 100 : 0}%` }} /><span className="bg-cyan-400" style={{ width: `${tokens ? completion / tokens * 100 : 0}%` }} /></div>
      <div className="mt-2 flex gap-3 text-[10px] text-slate-500"><span className="text-violet-300">● Prompt ({prompt.toLocaleString()})</span><span className="text-cyan-300">● Completion ({completion.toLocaleString()})</span></div>
    </section>
    <section className="mt-auto rounded-lg border border-(--border) bg-(--surface) p-3">
      <div className="flex items-center justify-between"><h3 className="text-xs font-semibold">Final report</h3>{!run?.final_report && <LockKeyhole size={14} className="text-slate-600" />}</div>
      {run?.final_report ? <div className="dashboard-inspector-scroll prose mt-2 h-15 max-w-none overflow-auto text-xs prose-headings:text-slate-300 prose-p:text-slate-300 prose-strong:text-slate-300 prose-code:text-slate-300"><ReactMarkdown remarkPlugins={[remarkGfm]}>{run.final_report}</ReactMarkdown></div>
        : <p className="mt-2 text-xs leading-5 text-slate-500">The workflow summary artifact will be generated automatically once the run completes.</p>}
    </section>
    <p className="flex items-center justify-center gap-1 text-[10px] text-slate-600"><Activity size={12} />{run ? "Persisted run data · live updates" : "Waiting for a run"}</p>
  </aside>;
}

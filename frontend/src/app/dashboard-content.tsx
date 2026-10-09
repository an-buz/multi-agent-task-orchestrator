"use client";

import {
  Check,
  CloudUpload,
  FileText,
  Paperclip,
  Play,
  Sparkles,
  X,
} from "lucide-react";
import { useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Sidebar } from "@/components/sidebar";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useWorkflows } from "@/features/workflows/queries";
import { cancelRun, confirmRun, createRun, editRunPlan, runsQueryKey, waitForRunPlan } from "@/features/runs/api";
import { runSteps, useRunMonitor } from "@/features/monitor/use-run-monitor";
import { RunPipeline, RunConsole, RunInspector } from "@/features/monitor/dashboard-monitor";
import type { RunDetails } from "@/features/runs/types";
import { useUploadContextFile, useDeleteContextFile, type ContextFile } from "@/features/files/queries";

export default function DashboardPage() {
  const [task, setTask] = useState(
    "Analyze current repository issues, write a summary report for the QA tester, run unit tests via code executor, and compile final markdown release notes.",
  );
  const [context, setContext] = useState("");
  const [attachments, setAttachments] = useState<ContextFile[]>([]);
  const uploadFile = useUploadContextFile();
  const deleteFile = useDeleteContextFile();
  const fileBusy = uploadFile.isPending || deleteFile.isPending;
  const [contextOpen, setContextOpen] = useState(false);
  const router = useRouter();
  const client = useQueryClient();
  const params = useSearchParams();
  const monitor = useRunMonitor(params.get("run"));
  const monitoredRun = monitor.run;
  const monitoredSteps = runSteps(monitoredRun);
  const [inspected, setInspected] = useState<{ runId: string; number: number } | null>(null);
  const inspectedStep = (inspected?.runId === monitoredRun?.id
    ? monitoredSteps.find((step) => step.step_number === inspected?.number) : undefined)
    ?? monitoredSteps.find((step) => step.status === "IN_PROGRESS")
    ?? monitoredSteps.find((step) => step.status === "FAILED") ?? monitoredSteps[0];
  const workflowsQuery = useWorkflows();
  const [workflowId, setWorkflowId] = useState("");
  const [runDraft, setRunDraft] = useState<RunDetails | null>(null);
  const [runError, setRunError] = useState("");
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  async function handleFile(file: File | undefined) {
    if (!file) return;
    setRunError("");
    try {
      const uploaded = await uploadFile.mutateAsync(file);
      setAttachments((current) => [...current, uploaded]);
      setContextOpen(true);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "Could not upload the context file.");
    } finally {
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function removeFile(file: ContextFile) {
    setRunError("");
    try {
      await deleteFile.mutateAsync(file.id);
      setAttachments((current) => current.filter((item) => item.id !== file.id));
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "Could not remove the context file.");
    }
  }

  async function createPlan() {
    if (!workflowId || !task.trim()) {
      setRunError("Choose a workflow and enter a task.");
      return;
    }
    setBusy(true);
    setRunError("");
    try {
      const created = await createRun({
        workflow_id: workflowId,
        task: task.trim(),
        context_text: context || undefined,
        file_ids: attachments.map((file) => file.id),
      });
      router.replace(`/?run=${encodeURIComponent(created.id)}`, { scroll: false });
      await client.invalidateQueries({ queryKey: runsQueryKey, exact: true });
      // The run now owns immutable references; removing draft attachments must not delete them.
      setAttachments([]);
      const draft = "plan" in created && created.plan ? created : await waitForRunPlan(created.id);
      setRunDraft(draft);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "Could not create a run.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmPlan() {
    if (!runDraft) return;
    setBusy(true);
    try {
      if (runDraft.plan) {
        const steps = Array.isArray(runDraft.plan) ? runDraft.plan : runDraft.plan.steps;
        await editRunPlan(runDraft.id, steps);
      }
      const run = await confirmRun(runDraft.id);
      client.setQueryData([...runsQueryKey, run.id], run);
      setRunDraft(null);
      router.replace(`/?run=${encodeURIComponent(run.id)}`, { scroll: false });
      await client.invalidateQueries({ queryKey: runsQueryKey, exact: true });
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "Could not start the run.");
    } finally {
      setBusy(false);
    }
  }

  async function cancelPlan() {
    if (!runDraft) return;
    setBusy(true);
    setRunError("");
    try {
      const cancelled = await cancelRun(runDraft.id);
      client.setQueryData([...runsQueryKey, cancelled.id], cancelled);
      await client.invalidateQueries({ queryKey: runsQueryKey, exact: true });
      setRunDraft(null);
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "Could not cancel the run.");
    } finally {
      setBusy(false);
    }
  }

  const planSteps = runDraft?.plan
    ? Array.isArray(runDraft.plan)
      ? runDraft.plan
      : runDraft.plan.steps
    : [];

  return (
    <main className="min-h-screen bg-[#050816] lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <Sidebar />
      <section className="min-w-0">
        <header className="flex min-h-20 flex-wrap items-center justify-between gap-3 border-b border-(--border) px-6 py-4 lg:px-8">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Orchestration Center</h1>
            <p className="mt-1 text-xs text-slate-400">
              Active Session: <span className="font-mono text-slate-300">{monitor.runId ?? "No run selected"}</span>
            </p>
          </div>
          <div className="flex items-center gap-5 text-xs text-slate-300">
            <span className="flex items-center gap-2">
              <i className="size-2 rounded-full bg-emerald-400" />
              Completed: {monitoredSteps.filter((step) => step.status === "COMPLETED").length}
            </span>
            <span className="flex items-center gap-2">
              <i className="size-2 rounded-full bg-amber-400" />
              Active Nodes: {monitoredSteps.filter((step) => step.status === "IN_PROGRESS").length}
            </span>
          </div>
        </header>
        <div className="grid min-h-[calc(100vh-80px)] xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0 space-y-5 p-5 lg:p-6">
            <section className="rounded-xl border border-(--border) bg-(--surface) p-4 lg:p-5">
              <label
                htmlFor="workflow-task"
                className="text-[11px] font-semibold uppercase tracking-wide text-slate-400"
              >
                Workflow task definition
              </label>
              <Textarea
                id="workflow-task"
                value={task}
                onChange={(event) => setTask(event.target.value)}
                placeholder="Describe the task you want your workflow to complete..."
                rows={3}
                className="mt-2.5 min-h-24 w-full resize-y rounded-lg border border-(--border) bg-[#050816] px-3 py-3 text-sm leading-6 text-slate-200 outline-none placeholder:text-slate-600 focus:border-emerald-500/60"
              />
              {contextOpen && (
                <div className="mt-3 rounded-lg border border-(--border) bg-[#080e1d] p-3">
                  <div className="mb-2 flex items-center justify-between text-xs text-slate-400">
                    <span className="flex items-center gap-2">
                      <Paperclip size={13} />
                      Additional context
                    </span>
                    <Button
                      variant="ghost"
                      onClick={() => setContextOpen(false)}
                      aria-label="Close context"
                      className="rounded p-1 hover:bg-white/5 [&_svg]:size-4"
                    >
                      <X size={14} />
                    </Button>
                  </div>
                  {attachments.map((attachment) => (
                    <div key={attachment.id} className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
                      <FileText size={13} />
                      {attachment.filename} ({attachment.size_bytes} bytes)
                      <Button
                        variant="ghost"
                        aria-label={`Remove attachment ${attachment.filename}`}
                        disabled={fileBusy || busy}
                        onClick={() => void removeFile(attachment)}
                        className="[&_svg]:size-3.25"
                      >
                        <X size={13} />
                      </Button>
                    </div>
                  ))}
                  <Textarea
                    value={context}
                    onChange={(event) => setContext(event.target.value)}
                    rows={3}
                    placeholder="Paste context here..."
                    className="w-full resize-y bg-transparent text-sm leading-5 text-slate-300 outline-none placeholder:text-slate-600"
                  />
                </div>
              )}
              <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Select value={workflowId || null} onValueChange={(value) => setWorkflowId(value ?? "")}>
                    <SelectTrigger aria-label="Workflow" className="h-auto w-auto rounded-lg border-(--border) bg-[#050816] px-3 py-2 text-xs text-slate-300">
                      {workflowsQuery.data?.items.find((workflow) => workflow.id === workflowId)?.title ?? "Choose workflow"}
                    </SelectTrigger>
                    <SelectContent>
                    <SelectGroup>
                    {workflowsQuery.data?.items.map((workflow) => (
                      <SelectItem key={workflow.id} value={workflow.id}>{workflow.title}</SelectItem>
                    ))}
                    </SelectGroup>
                    </SelectContent>
                  </Select>
                  <input
                    ref={fileInput}
                    type="file"
                    accept=".txt,.md,.json,.pdf,text/plain,text/markdown,application/json,application/pdf"
                    className="hidden"
                    disabled={fileBusy || busy || attachments.length >= 10}
                    onChange={(event) => void handleFile(event.target.files?.[0])}
                  />
                  <Button disabled={fileBusy || busy || attachments.length >= 10} onClick={() => fileInput.current?.click()} variant="secondary">
                    <CloudUpload data-icon="inline-start" />
                    {uploadFile.isPending ? "Uploading…" : "Add context file"} <span className="text-muted-foreground">TXT · MD · JSON · PDF</span>
                  </Button>
                  <Button onClick={() => setContextOpen(true)} variant="ghost">
                    Paste text
                  </Button>
                  {attachments.length > 0 && (
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Check size={12} />
                      {attachments.length} attached
                    </span>
                  )}
                </div>
                <Button type="button" disabled={busy || fileBusy} onClick={() => void createPlan()}>
                  <Sparkles size={16} />
                  {busy ? "Preparing…" : "Decompose and Run"}
                  <Play size={14} />
                </Button>
              </div>
              {runError && (
                <p role="alert" className="mt-3 text-xs text-rose-300">
                  {runError}
                </p>
              )}
              {workflowsQuery.isError && (
                <p role="alert" className="mt-2 text-xs text-rose-300">
                  Could not load workflows.
                </p>
              )}
              {runDraft && (
                <div
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby="plan-title"
                  className="mt-4 rounded-lg border border-emerald-500/30 bg-[#080e1d] p-4"
                >
                  <div className="flex items-center justify-between">
                    <h2 id="plan-title" className="text-sm font-semibold">
                      Plan preview
                    </h2>
                    <Button
                      variant="ghost"
                      aria-label="Close plan"
                      disabled={busy}
                      onClick={() => void cancelPlan()}
                    >
                      <X size={15} />
                    </Button>
                  </div>
                  <ol className="mt-3 space-y-2">
                    {planSteps.map((step) => (
                      <li
                        key={step.step_number}
                        className="rounded border border-(--border) p-3 text-xs"
                      >
                        <span className="font-medium">
                          {step.step_number}. {step.agent_name}
                        </span>
                        <span className="ml-2 text-slate-400">
                          Depends on: {step.depends_on.length ? step.depends_on.join(", ") : "none"}
                        </span>
                        <textarea
                          aria-label={`Task for ${step.agent_name}`}
                          className="mt-2 block w-full rounded border border-(--border) bg-[#050816] p-2 text-slate-300"
                          value={step.input ?? step.subtask ?? ""}
                          onChange={(event) =>
                            setRunDraft({
                              ...runDraft,
                              plan: planSteps.map((item) =>
                                item.step_number === step.step_number
                                  ? {
                                      ...item,
                                      input: event.target.value,
                                      subtask: event.target.value,
                                    }
                                  : item,
                              ),
                            })
                          }
                        />
                      </li>
                    ))}
                  </ol>
                  <div className="mt-3 flex justify-end gap-2">
                    <Button variant="secondary" disabled={busy} onClick={() => void cancelPlan()}>
                      Cancel
                    </Button>
                    <Button disabled={busy} onClick={() => void confirmPlan()}>
                      {busy ? "Starting…" : "Confirm and run"}
                    </Button>
                  </div>
                </div>
              )}
            </section>
            {monitor.runs.isError && <p role="alert" className="text-sm text-destructive">Could not load runs.</p>}
            {monitor.detail.isError && <p role="alert" className="text-sm text-destructive">Could not load the selected run.</p>}
            {(monitor.runs.isLoading || monitor.detail.isLoading) && <p role="status" className="text-sm text-muted-foreground">Loading monitoring data…</p>}
            <RunPipeline run={monitoredRun} runs={monitor.runs.data?.items ?? []}
              pending={monitor.runs.isLoading || monitor.detail.isLoading}
              failed={monitor.runs.isError || monitor.detail.isError}
              selectRun={(id) => router.replace(`/?run=${encodeURIComponent(id)}`, { scroll: false })}
              step={inspectedStep} selectStep={(number) => {
                if (monitoredRun) setInspected({ runId: monitoredRun.id, number });
              }} />
            <RunConsole runId={monitor.runId} events={monitor.events} connectionError={monitor.connectionError} steps={monitoredSteps} />
          </div>
          <RunInspector run={monitoredRun} step={inspectedStep} />
        </div>
      </section>
    </main>
  );
}

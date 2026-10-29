"use client";

import { RunDecisions } from "@/features/runs/run-decisions";

import { Check, CloudUpload, FileText, Paperclip, Play, Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useWorkflows } from "@/features/workflows/queries";
import { createRun, waitForRunPlan } from "@/features/runs/api";
import { cacheRun, runsQueryKey } from "@/features/runs/cache";
import { dashboardInspectorStep, runSteps } from "@/features/runs/model";
import { useRunMonitor } from "@/features/monitor/use-run-monitor";
import { RunPipeline, RunConsole, RunInspector } from "@/features/monitor/dashboard-monitor";
import { PlanPreview } from "@/features/runs/plan-preview";

import type { ContextFile } from "@/features/files/types";

import { useUploadContextFile, useDeleteContextFile } from "@/features/files/queries";

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

  const inspectedStep = dashboardInspectorStep(
    monitoredRun,
    monitor.activationOrder,
    inspected?.runId === monitoredRun?.id ? inspected?.number : undefined,
  );

  const workflowsQuery = useWorkflows();

  const [workflowId, setWorkflowId] = useState("");
  const [runError, setRunError] = useState("");
  const [busy, setBusy] = useState(false);

  const fileInput = useRef<HTMLInputElement>(null);
  const planningWait = useRef<AbortController | null>(null);

  useEffect(() => () => planningWait.current?.abort(), []);

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

    const controller = new AbortController();

    planningWait.current?.abort();
    planningWait.current = controller;

    try {
      const created = await createRun({
        workflow_id: workflowId,
        task: task.trim(),
        context_text: context || undefined,
        file_ids: attachments.map((file) => file.id),
      });

      // Detach local upload state as soon as the server owns the references.
      setAttachments([]);

      if (controller.signal.aborted) return;

      router.replace(`/?run=${encodeURIComponent(created.id)}`, { scroll: false });

      await client.invalidateQueries({ queryKey: [...runsQueryKey, "list"] });

      const draft =
        "plan" in created && created.plan
          ? created
          : await waitForRunPlan(created.id, controller.signal);

      if (!controller.signal.aborted) {
        await cacheRun(client, draft);
      }
    } catch (error) {
      if (!controller.signal.aborted)
        setRunError(error instanceof Error ? error.message : "Could not create a run.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell>
      <section className="flex min-h-screen min-w-0 flex-col">
        <header className="flex min-h-20 shrink-0 flex-wrap items-center justify-between gap-3 border-b border-border px-6 py-4 lg:px-8">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Orchestration Center</h1>
            <p className="mt-1 text-xs text-muted-foreground">
              Active Session:{" "}
              <span className="font-mono text-foreground">
                {monitor.runId ?? "No run selected"}
              </span>
            </p>
          </div>
          <div className="flex items-center gap-5 text-xs text-foreground">
            <span className="flex items-center gap-2">
              <i className="size-2 rounded-full bg-status-completed" />
              Completed: {monitoredSteps.filter((step) => step.status === "COMPLETED").length}
            </span>
            <span className="flex items-center gap-2">
              <i className="size-2 rounded-full bg-status-warning" />
              Active Nodes: {monitoredSteps.filter((step) => step.status === "IN_PROGRESS").length}
            </span>
          </div>
        </header>
        <div className="grid flex-1 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0 space-y-5 p-5 lg:p-6">
            {monitoredRun && <RunDecisions run={monitoredRun} />}
            {monitoredRun?.status === "AWAITING_CONFIRMATION" && monitoredRun.plan && (
              <PlanPreview key={monitoredRun.id} run={monitoredRun} />
            )}
            <section className="rounded-xl border border-border bg-card p-4 lg:p-5">
              <label
                htmlFor="workflow-task"
                className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
              >
                Workflow task definition
              </label>
              <Textarea
                id="workflow-task"
                value={task}
                onChange={(event) => setTask(event.target.value)}
                placeholder="Describe the task you want your workflow to complete..."
                rows={3}
                className="mt-2.5 min-h-24 w-full resize-y rounded-lg border border-border bg-background px-3 py-3 text-sm leading-6 text-foreground outline-none placeholder:text-muted-foreground focus:border-status-completed/60"
              />
              {contextOpen && (
                <div className="mt-3 rounded-lg border border-border bg-background p-3">
                  <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
                    <span className="flex items-center gap-2">
                      <Paperclip size={13} />
                      Additional context
                    </span>
                    <Button
                      variant="ghost"
                      onClick={() => setContextOpen(false)}
                      aria-label="Close context"
                      className="rounded p-1 hover:bg-foreground/5 [&_svg]:size-4"
                    >
                      <X size={14} />
                    </Button>
                  </div>
                  {attachments.map((attachment) => (
                    <div
                      key={attachment.id}
                      className="mb-2 flex items-center gap-2 text-xs text-muted-foreground"
                    >
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
                    className="w-full resize-y bg-transparent text-sm leading-5 text-foreground outline-none placeholder:text-muted-foreground"
                  />
                </div>
              )}
              <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                <div className="flex min-w-0 max-w-full flex-wrap items-center gap-2">
                  <Select
                    value={workflowId || null}
                    onValueChange={(value) => setWorkflowId(value ?? "")}
                  >
                    <SelectTrigger
                      aria-label="Workflow"
                      className="h-auto w-auto max-w-full rounded-lg border-border bg-background px-3 py-2 text-xs text-foreground"
                    >
                      <span className="truncate">
                        {workflowsQuery.data?.items.find((workflow) => workflow.id === workflowId)
                          ?.title ?? "Choose workflow"}
                      </span>
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        {workflowsQuery.data?.items.map((workflow) => (
                          <SelectItem key={workflow.id} value={workflow.id}>
                            {workflow.title}
                          </SelectItem>
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
                  <Button
                    disabled={fileBusy || busy || attachments.length >= 10}
                    onClick={() => fileInput.current?.click()}
                    variant="secondary"
                  >
                    <CloudUpload data-icon="inline-start" />
                    {uploadFile.isPending ? "Uploading…" : "Add context file"}{" "}
                    <span className="text-muted-foreground">TXT · MD · JSON · PDF</span>
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
                <p role="alert" className="mt-3 text-xs text-destructive">
                  {runError}
                </p>
              )}
              {workflowsQuery.isError && (
                <p role="alert" className="mt-2 text-xs text-destructive">
                  Could not load workflows.
                </p>
              )}
            </section>
            {monitor.runs.isError && (
              <p role="alert" className="text-sm text-destructive">
                Could not load runs.
              </p>
            )}
            {monitor.detail.isError && (
              <p role="alert" className="text-sm text-destructive">
                Could not load the selected run.
              </p>
            )}
            {(monitor.runs.isLoading || monitor.detail.isLoading) && (
              <p role="status" className="text-sm text-muted-foreground">
                Loading monitoring data…
              </p>
            )}
            <RunPipeline
              run={monitoredRun}
              runs={monitor.runs.data?.items ?? []}
              pending={monitor.runs.isLoading || monitor.detail.isLoading}
              failed={monitor.runs.isError || monitor.detail.isError}
              selectRun={(id) =>
                router.replace(`/?run=${encodeURIComponent(id)}`, { scroll: false })
              }
              step={inspectedStep}
              selectStep={(number) => {
                if (monitoredRun) setInspected({ runId: monitoredRun.id, number });
              }}
            />
            <RunConsole
              runId={monitor.runId}
              events={monitor.activityEvents}
              connectionError={monitor.connectionError}
              steps={monitoredSteps}
            />
          </div>
          <RunInspector run={monitoredRun} step={inspectedStep} />
        </div>
      </section>
    </AppShell>
  );
}

"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Sidebar } from "@/components/sidebar";
import {
  cancelRun,
  exportRun,
  getRun,
  retryRunStep,
  runsQueryKey,
  subscribeToRun,
} from "@/features/runs/api";

export default function RunDetailContent({ id }: { id: string }) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: [...runsQueryKey, id],
    queryFn: () => getRun(id),
    refetchInterval: 3000,
  });
  const [events, setEvents] = useState<string[]>([]);
  const [streamError, setStreamError] = useState(false);
  useEffect(
    () =>
      subscribeToRun(
        id,
        (event) => {
          setStreamError(false);
          setEvents((current) =>
            [
              ...current,
              `${new Date(event.ts ?? event.timestamp ?? new Date().toISOString()).toLocaleTimeString()} ${event.event}`,
            ].slice(-150),
          );
          void client.invalidateQueries({ queryKey: [...runsQueryKey, id] });
        },
        () => setStreamError(true),
      ),
    [id, client],
  );

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
  const runSteps = run?.plan ? (Array.isArray(run.plan) ? run.plan : run.plan.steps) : [];
  return (
    <main className="min-h-screen lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <Sidebar />
      <section className="min-w-0">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-(--border) px-6 py-5 lg:px-8">
          <div>
            <h1 className="text-xl font-semibold">Run details</h1>
            <p className="mt-1 font-mono text-xs text-slate-400">{id}</p>
          </div>
          {run && (
            <div className="flex gap-2">
              <span className="self-center font-mono text-xs">{run.status}</span>
              {run.status === "IN_PROGRESS" && (
                <button
                  className="rounded border border-(--border) px-3 py-2 text-xs"
                  onClick={() => void cancelRun(id).then(() => query.refetch())}
                >
                  Cancel run
                </button>
              )}
            </div>
          )}
        </header>
        <div className="space-y-5 p-6 lg:p-8">
          {query.isLoading && <p>Loading run…</p>}
          {query.isError && (
            <p role="alert" className="text-rose-400">
              Could not load this run.
            </p>
          )}
          {run && (
            <>
              <section className="rounded-xl border border-(--border) bg-(--surface) p-5">
                <h2 className="text-sm font-semibold">Task</h2>
                <p className="mt-2 whitespace-pre-wrap text-sm text-slate-300">{run.task}</p>
                {run.context_text && (
                  <pre className="mt-3 overflow-auto rounded bg-[#050816] p-3 text-xs text-slate-400">
                    {run.context_text}
                  </pre>
                )}
              </section>
              <section className="rounded-xl border border-(--border) bg-(--surface) p-5">
                <h2 className="mb-3 text-sm font-semibold">Execution steps</h2>
                <div className="space-y-3">
                  {runSteps.map((step) => (
                    <article
                      key={step.step_number}
                      className="rounded-lg border border-(--border) p-4"
                    >
                      <div className="flex flex-wrap justify-between gap-2">
                        <h3 className="text-sm font-medium">
                          {step.step_number}. {step.agent_name}
                        </h3>
                        <span className="font-mono text-xs">{step.status}</span>
                      </div>
                      {step.input && (
                        <p className="mt-2 text-xs text-slate-400">Input: {step.input}</p>
                      )}
                      {step.output && (
                        <p className="mt-2 whitespace-pre-wrap text-sm text-slate-300">
                          {step.output}
                        </p>
                      )}
                      {step.error && (
                        <p role="alert" className="mt-2 text-xs text-rose-300">
                          {step.error.message}
                        </p>
                      )}
                      {step.retryable && (
                        <button
                          className="mt-3 text-xs text-emerald-300 underline"
                          onClick={() =>
                            void retryRunStep(id, step.step_number).then(() => query.refetch())
                          }
                        >
                          Retry step
                        </button>
                      )}
                    </article>
                  ))}
                </div>
              </section>
              {run.final_report && (
                <section className="prose prose-invert max-w-none rounded-xl border border-(--border) bg-(--surface) p-5">
                  <h2>Final report</h2>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{run.final_report}</ReactMarkdown>
                </section>
              )}
              <section className="rounded-xl border border-(--border) bg-[#050816] p-5">
                <h2 className="text-sm font-semibold">Live events</h2>
                {streamError && (
                  <p role="status" className="mt-2 text-xs text-amber-300">
                    Connection lost. Reconnecting…
                  </p>
                )}
                <div
                  aria-live="polite"
                  className="mt-3 max-h-56 space-y-1 overflow-auto font-mono text-xs text-slate-400"
                >
                  {events.map((event, i) => (
                    <p key={`${event}-${i}`}>{event}</p>
                  ))}
                </div>
              </section>
              {run.final_report && (
                <div className="flex flex-wrap gap-2">
                  {(["json", "md", "pdf"] as const).map((format) => (
                    <button
                      key={format}
                      className="rounded border border-(--border) px-3 py-2 text-xs uppercase"
                      onClick={() => void download(format)}
                    >
                      {format === "md"
                        ? "Download MD"
                        : format === "pdf"
                          ? "Download PDF"
                          : "Download JSON"}
                    </button>
                  ))}
                  <button
                    className="rounded border border-(--border) px-3 py-2 text-xs"
                    onClick={() => void navigator.clipboard.writeText(run.final_report ?? "")}
                  >
                    Copy Markdown
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </section>
    </main>
  );
}

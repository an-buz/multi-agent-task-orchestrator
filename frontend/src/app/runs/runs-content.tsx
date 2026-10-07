"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Sidebar } from "@/components/sidebar";
import { runsQueryKey, listRuns } from "@/features/runs/api";

export default function RunsContent() {
  const query = useQuery({ queryKey: runsQueryKey, queryFn: listRuns });
  return (
    <main className="min-h-screen lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <Sidebar />
      <section className="min-w-0">
        <header className="border-b border-(--border) px-6 py-6 lg:px-8">
          <h1 className="text-xl font-semibold">Runs</h1>
          <p className="mt-1 text-xs text-slate-400">Execution history and results.</p>
        </header>
        <div className="space-y-3 p-6 lg:p-8">
          {query.isLoading && <p className="text-sm text-slate-400">Loading runs…</p>}
          {query.isError && (
            <div role="alert" className="text-sm text-rose-400">
              Could not load runs.{" "}
              <button className="underline" onClick={() => void query.refetch()}>
                Try again
              </button>
            </div>
          )}
          {query.data?.items.map((run) => (
            <Link
              key={run.id}
              href={`/runs/${run.id}`}
              className="block rounded-xl border border-(--border) bg-(--surface) p-4 hover:border-emerald-500/50"
            >
              <div className="flex flex-wrap justify-between gap-2">
                <h2 className="text-sm font-semibold">{run.workflow_title ?? run.task}</h2>
                <span className="font-mono text-xs text-slate-300">{run.status}</span>
              </div>
              <p className="mt-2 line-clamp-2 text-xs text-slate-400">{run.task}</p>
              <p className="mt-3 font-mono text-[10px] text-slate-500">
                {new Date(run.created_at).toLocaleString()} · {run.total_tokens.toLocaleString()}{" "}
                tokens
              </p>
            </Link>
          ))}
          {query.data?.items.length === 0 && (
            <div className="rounded-xl border border-dashed border-(--border) p-8 text-center text-sm text-slate-400">
              No runs yet. Start a workflow from the dashboard.
            </div>
          )}
        </div>
      </section>
    </main>
  );
}

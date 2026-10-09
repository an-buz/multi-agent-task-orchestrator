"use client";

import Link from "next/link";
import { useState } from "react";
import { Trash2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { DeleteConfirmationDialog } from "@/components/delete-confirmation-dialog";
import { StatusBadge } from "@/components/status-badge";
import { Sidebar } from "@/components/sidebar";
import { runsQueryKey, listRuns, deleteRun } from "@/features/runs/api";
import type { RunDetails, RunListResponse } from "@/features/runs/types";

export default function RunsContent() {
  const client = useQueryClient();
  const [deleting, setDeleting] = useState<RunDetails | null>(null);
  const query = useQuery({ queryKey: runsQueryKey, queryFn: listRuns, refetchInterval: 5000 });
  const deletion = useMutation({
    mutationFn: deleteRun,
    onSuccess: async (_, id) => {
      await client.cancelQueries({ queryKey: [...runsQueryKey, id] });
      client.removeQueries({ queryKey: [...runsQueryKey, id] });
      client.setQueryData<RunListResponse>(runsQueryKey, (current) => current ? {
        ...current, items: current.items.filter((run) => run.id !== id), total: current.total - 1,
      } : current);
      void client.invalidateQueries({ queryKey: runsQueryKey, exact: true });
    },
  });
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
            <div key={run.id} className="flex items-center gap-2 rounded-xl border border-border bg-(--surface) p-4">
            <Link
              href={`/runs/${run.id}`}
              className="block min-w-0 flex-1"
            >
              <div className="flex flex-wrap justify-between gap-2">
                <h2 className="text-sm font-semibold">{run.workflow_title ?? run.task}</h2>
                <StatusBadge status={run.status} />
              </div>
              <p className="mt-2 line-clamp-2 text-xs text-slate-400">{run.task}</p>
              <p className="mt-3 font-mono text-[10px] text-slate-500">
                {new Date(run.created_at).toLocaleString()} · {run.total_tokens.toLocaleString()}{" "}
                tokens
              </p>
            </Link>
            <Button
              variant="ghost"
              size="icon"
              aria-label={`Delete run ${run.id}`}
              disabled={!["AWAITING_CONFIRMATION", "COMPLETED", "FAILED", "CANCELLED"].includes(run.status)}
              title={["AWAITING_CONFIRMATION", "COMPLETED", "FAILED", "CANCELLED"].includes(run.status)
                ? "Delete run" : "Cancel the run from its details before deleting it"}
              onClick={() => setDeleting(run)}
            >
              <Trash2 />
            </Button>
            </div>
          ))}
          {query.data?.items.length === 0 && (
            <div className="rounded-xl border border-dashed border-(--border) p-8 text-center text-sm text-slate-400">
              No runs yet. Start a workflow from the dashboard.
            </div>
          )}
        </div>
      </section>
      {deleting && <DeleteConfirmationDialog
        key={deleting.id}
        name={deleting.task}
        entity="run"
        description="Its results, steps, and event history will also be deleted. Uploaded files will be kept."
        pending={deletion.isPending}
        onClose={() => setDeleting(null)}
        onConfirm={() => deletion.mutateAsync(deleting.id)}
      />}
    </main>
  );
}

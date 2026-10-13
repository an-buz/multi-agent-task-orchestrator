"use client";

import Link from "next/link";
import { useState } from "react";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DeleteConfirmationDialog } from "@/components/delete-confirmation-dialog";
import { StatusBadge } from "@/components/status-badge";
import { AppShell } from "@/components/app-shell";
import { useRuns, useDeleteRun } from "./queries";
import type { RunDetails } from "@/features/runs/types";

export default function RunsContent() {
  const [deleting, setDeleting] = useState<RunDetails | null>(null);
  const query = useRuns();
  const deletion = useDeleteRun();
  return (
    <AppShell>
      <section className="min-w-0">
        <header className="border-b border-(--border) px-6 py-6 lg:px-8">
          <h1 className="text-xl font-semibold">Runs</h1>
          <p className="mt-1 text-xs text-muted-foreground">Execution history and results.</p>
        </header>
        <div className="space-y-3 p-6 lg:p-8">
          {query.isLoading && <p className="text-sm text-muted-foreground">Loading runs…</p>}
          {query.isError && (
            <div role="alert" className="text-sm text-destructive">
              Could not load runs.{" "}
              <button className="underline" onClick={() => void query.refetch()}>
                Try again
              </button>
            </div>
          )}
          {query.data?.items.map((run) => (
            <div
              key={run.id}
              className="flex items-center gap-2 rounded-xl border border-border bg-card p-4"
            >
              <Link href={`/runs/${run.id}`} className="block min-w-0 flex-1">
                <div className="flex flex-wrap justify-between gap-2">
                  <h2 className="text-sm font-semibold">{run.workflow_title ?? run.task}</h2>
                  <StatusBadge status={run.status} />
                </div>
                <p className="mt-2 line-clamp-2 text-xs text-muted-foreground">{run.task}</p>
                <p className="mt-3 font-mono text-[10px] text-muted-foreground">
                  {new Date(run.created_at).toLocaleString()} · {run.total_tokens.toLocaleString()}{" "}
                  tokens
                </p>
              </Link>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Delete run ${run.id}`}
                disabled={
                  !["AWAITING_CONFIRMATION", "COMPLETED", "FAILED", "CANCELLED"].includes(
                    run.status,
                  )
                }
                title={
                  ["AWAITING_CONFIRMATION", "COMPLETED", "FAILED", "CANCELLED"].includes(run.status)
                    ? "Delete run"
                    : "Cancel the run from its details before deleting it"
                }
                onClick={() => setDeleting(run)}
              >
                <Trash2 />
              </Button>
            </div>
          ))}
          {query.data?.items.length === 0 && (
            <div className="rounded-xl border border-dashed border-(--border) p-8 text-center text-sm text-muted-foreground">
              No runs yet. Start a workflow from the dashboard.
            </div>
          )}
        </div>
      </section>
      {deleting && (
        <DeleteConfirmationDialog
          key={deleting.id}
          name={deleting.task}
          entity="run"
          description="Its results, steps, and event history will also be deleted. Uploaded files will be kept."
          pending={deletion.isPending}
          onClose={() => setDeleting(null)}
          onConfirm={() => deletion.mutateAsync(deleting.id)}
        />
      )}
    </AppShell>
  );
}

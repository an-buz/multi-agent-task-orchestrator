"use client";

import { useRuns } from "@/features/runs/queries";
import { useRunEvents } from "@/features/runs/use-run-events";

export function useRunMonitor(selectedId: string | null) {
  const runs = useRuns();

  const items = runs.data?.items ?? [];
  const runId =
    selectedId ??
    items.find((run) =>
      ["PLANNING", "IN_PROGRESS", "AWAITING_CONFIRMATION", "PAUSED"].includes(run.status),
    )?.id ??
    items[0]?.id;

  const events = useRunEvents(runId);
  const detail = events.query;

  return { runs, detail, run: detail.data, runId, ...events };
}

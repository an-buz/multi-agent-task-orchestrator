"use client";

import { useEffect } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { useRuns } from "@/features/runs/queries";
import { useRunEvents } from "@/features/runs/use-run-events";

export function useRunMonitor(selectedId: string | null) {
  const runs = useRuns();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const items = runs.data?.items ?? [];
  const latestRunId =
    items.find((run) =>
      ["PLANNING", "IN_PROGRESS", "AWAITING_CONFIRMATION", "PAUSED"].includes(run.status),
    )?.id ?? items[0]?.id;
  const runId = selectedId ?? undefined;

  useEffect(() => {
    if (selectedId || !latestRunId) return;

    const nextParams = new URLSearchParams(params.toString());

    nextParams.set("run", latestRunId);
    router.replace(`${pathname}?${nextParams}`, { scroll: false });
  }, [selectedId, latestRunId, params, pathname, router]);

  function followLatestRun() {
    if (!latestRunId) return;

    const nextParams = new URLSearchParams(params.toString());

    nextParams.set("run", latestRunId);
    router.replace(`${pathname}?${nextParams}`, { scroll: false });
  }

  const events = useRunEvents(runId);
  const detail = events.query;

  return { runs, detail, run: detail.data, runId, latestRunId, followLatestRun, ...events };
}

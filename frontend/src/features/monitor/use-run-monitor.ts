"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getRun, listRuns, runsQueryKey, subscribeToRun } from "@/features/runs/api";
import type { RunDetails, RunEvent, RunStep } from "@/features/runs/types";

export function runSteps(run: RunDetails | undefined): RunStep[] {
  return run?.plan ? (Array.isArray(run.plan) ? run.plan : run.plan.steps) : [];
}

export function eventKey(event: RunEvent): string {
  return event.id ?? JSON.stringify(event);
}

export function useRunMonitor(selectedId: string | null) {
  const client = useQueryClient();
  const runs = useQuery({ queryKey: runsQueryKey, queryFn: listRuns, refetchInterval: 5000 });
  const items = runs.data?.items ?? [];
  const runId = selectedId ?? items.find((run) =>
    ["PLANNING", "IN_PROGRESS", "AWAITING_CONFIRMATION"].includes(run.status))?.id ?? items[0]?.id;
  const detail = useQuery({
    queryKey: [...runsQueryKey, runId],
    queryFn: () => getRun(runId!),
    enabled: Boolean(runId),
    refetchInterval: 3000,
  });
  const log = useQuery<RunEvent[]>({
    queryKey: [...runsQueryKey, runId, "events"],
    queryFn: () => [], initialData: [], enabled: false,
  });
  const [connectionError, setConnectionError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    const key = [...runsQueryKey, runId];
    return subscribeToRun(runId, (event) => {
      setConnectionError(null);
      client.setQueryData<RunEvent[]>([...key, "events"], (current = []) =>
        current.some((item) => eventKey(item) === eventKey(event))
          ? current : [...current, event].slice(-150));
      const data = event.data ?? event.payload;
      if (event.event === "run:snapshot") {
        if (data?.run && typeof data.run === "object" && "id" in data.run && data.run.id === runId) {
          void client.cancelQueries({ queryKey: key, exact: true });
          client.setQueryData(key, data.run);
        } else void client.invalidateQueries({ queryKey: key, exact: true });
        return;
      }
      if (event.event === "agent:stream_chunk" && data &&
          typeof data.stepNumber === "number" && typeof data.output === "string" &&
          typeof data.attempt === "number") {
        const number = data.stepNumber, output = data.output, attempt = data.attempt;
        void client.cancelQueries({ queryKey: key, exact: true });
        client.setQueryData<RunDetails>(key, (run) => {
          if (!run?.plan) return run;
          const steps = runSteps(run).map((step) => {
            if (step.step_number !== number || (step.attempt ?? 0) > attempt ||
                (["COMPLETED", "FAILED", "CANCELLED"].includes(step.status) &&
                  (step.attempt ?? 0) >= attempt)) return step;
            return { ...step, status: "IN_PROGRESS" as const, attempt, output };
          });
          return { ...run, plan: Array.isArray(run.plan) ? steps : { ...run.plan, steps } };
        });
        return;
      }
      void client.invalidateQueries({ queryKey: key, exact: true });
      if (event.event.startsWith("task:") || event.event === "plan:ready") {
        void client.invalidateQueries({ queryKey: runsQueryKey, exact: true });
      }
    }, () => setConnectionError(runId), { after: 0 });
  }, [runId, client]);

  return { runs, detail, run: detail.data, runId, events: log.data,
    connectionError: connectionError === runId };
}

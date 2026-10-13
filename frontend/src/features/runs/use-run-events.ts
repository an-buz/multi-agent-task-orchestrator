"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { subscribeToRun } from "./api";
import { applyStreamChunk, eventKey } from "./model";
import { runEventsQueryKey, runQueryKey, runsQueryKey } from "./queries";
import type { RunDetails, RunEvent } from "./types";

export function useRunEvents(runId: string | undefined) {
  const client = useQueryClient();
  const log = useQuery<RunEvent[]>({
    queryKey: runEventsQueryKey(runId),
    queryFn: () => [],
    initialData: [],
    enabled: false,
  });
  const [connectionError, setConnectionError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    const key = runQueryKey(runId);
    const previous = client.getQueryData<RunEvent[]>(runEventsQueryKey(runId)) ?? [];
    const lastId = previous.findLast((event) => event.id !== undefined)?.id;
    const after = lastId && /^\d+$/.test(lastId) ? Number(lastId) : 0;
    let active = true;
    const close = subscribeToRun(
      runId,
      (event) => {
        if (!active) return;
        setConnectionError(null);
        client.setQueryData<RunEvent[]>(runEventsQueryKey(runId), (current = []) =>
          current.some((item) => eventKey(item) === eventKey(event))
            ? current
            : [...current, event].slice(-150),
        );
        const data = event.data ?? event.payload;
        if (
          event.event === "run:snapshot" &&
          data?.run &&
          typeof data.run === "object" &&
          "id" in data.run &&
          data.run.id === runId
        ) {
          void client.cancelQueries({ queryKey: key, exact: true });
          client.setQueryData(key, data.run);
          return;
        }
        if (event.event === "agent:stream_chunk") {
          void client.cancelQueries({ queryKey: key, exact: true });
          client.setQueryData<RunDetails>(key, (run) => applyStreamChunk(run, event));
          return;
        }
        void client.invalidateQueries({ queryKey: key, exact: true });
        if (event.event.startsWith("task:") || event.event === "plan:ready") {
          void client.invalidateQueries({ queryKey: runsQueryKey, exact: true });
        }
      },
      () => {
        if (active) setConnectionError(runId);
      },
      { after },
    );
    return () => {
      active = false;
      close();
    };
  }, [runId, client]);

  return { events: log.data, connectionError: Boolean(runId) && connectionError === runId };
}

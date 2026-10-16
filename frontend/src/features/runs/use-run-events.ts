"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { subscribeToRun } from "./api";
import { appendRunEvent, applyStreamChunk, type RunEventLog } from "./model";
import { runEventsQueryKey, runQueryKey, runsQueryKey } from "./queries";
import type { RunDetails } from "./types";

export function useRunEvents(runId: string | undefined) {
  const client = useQueryClient();
  const log = useQuery<RunEventLog>({
    queryKey: runEventsQueryKey(runId),
    queryFn: () => ({ events: [], activityEvents: [], after: 0 }),
    initialData: { events: [], activityEvents: [], after: 0 },
    enabled: false,
  });
  const [connectionError, setConnectionError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    const key = runQueryKey(runId);
    const after = client.getQueryData<RunEventLog>(runEventsQueryKey(runId))?.after ?? 0;
    let active = true;
    const close = subscribeToRun(
      runId,
      (event) => {
        if (!active) return;
        setConnectionError(null);
        client.setQueryData<RunEventLog>(runEventsQueryKey(runId), (current) =>
          appendRunEvent(current ?? { events: [], activityEvents: [], after: 0 }, event),
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
          void client.invalidateQueries({ queryKey: [...runsQueryKey, "list"] });
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

  return {
    events: log.data.events,
    activityEvents: log.data.activityEvents,
    connectionError: Boolean(runId) && connectionError === runId,
  };
}

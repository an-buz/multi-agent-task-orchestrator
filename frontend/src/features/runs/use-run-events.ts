"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/lib/api";

import { subscribeToRun } from "./api";
import { appendRunEvent, applyStreamChunk, isTerminalRun, type RunEventLog } from "./model";
import { runEventsQueryKey, runQueryKey, runsQueryKey, useRun } from "./queries";

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

  const [connectedRun, setConnectedRun] = useState<string | null>(null);
  const query = useRun(runId, connectedRun !== runId || connectionError === runId);
  const isTerminal = isTerminalRun(query.data);
  const missing = query.error instanceof ApiError && query.error.status === 404;
  const enabled = Boolean(query.data) && !isTerminal && !missing;

  useEffect(() => {
    if (!runId || !enabled) return;

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

        if (
          event.event.startsWith("task:") ||
          event.event.startsWith("decision:") ||
          event.event === "plan:ready"
        ) {
          void client.invalidateQueries({ queryKey: [...runsQueryKey, "list"] });
        }
      },
      () => {
        if (active) setConnectionError(runId);
      },
      {
        after,
        onOpen: () => {
          if (active) {
            setConnectedRun(runId);
            setConnectionError(null);
          }
        },
      },
    );

    return () => {
      active = false;
      close();
    };
  }, [runId, client, isTerminal, enabled]);

  return {
    query,
    events: log.data.events,
    activityEvents: log.data.activityEvents,
    activationOrder: log.data.activationOrder ?? [],
    connectionError: enabled && Boolean(runId) && connectionError === runId,
  };
}

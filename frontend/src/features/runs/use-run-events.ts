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
    queryFn: () => ({ activityEvents: [], after: 0 }),
    initialData: { activityEvents: [], after: 0 },
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
    const after = client.getQueryData<RunEventLog>(runEventsQueryKey(runId))?.after || undefined;

    let active = true;
    let snapshotCursor = 0;
    let refreshTimer: ReturnType<typeof setTimeout> | undefined;
    let refreshList = false;

    const scheduleRefresh = (list: boolean) => {
      refreshList ||= list;
      if (refreshTimer !== undefined) return;

      refreshTimer = setTimeout(() => {
        refreshTimer = undefined;
        void client.invalidateQueries({ queryKey: key, exact: true }, { cancelRefetch: false });
        if (refreshList)
          void client.invalidateQueries(
            { queryKey: [...runsQueryKey, "list"] },
            { cancelRefetch: false },
          );
        refreshList = false;
      }, 300);
    };

    const close = subscribeToRun(
      runId,
      (event) => {
        if (!active) return;

        setConnectionError(null);

        const previousCursor =
          client.getQueryData<RunEventLog>(runEventsQueryKey(runId))?.after ?? 0;

        if (event.event === "agent:stream_chunk" && event.id && Number(event.id) <= previousCursor)
          return;

        client.setQueryData<RunEventLog>(runEventsQueryKey(runId), (current) =>
          appendRunEvent(current ?? { activityEvents: [], after: 0 }, event),
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
          snapshotCursor = typeof data.eventCursor === "number" ? data.eventCursor : 0;
          client.setQueryData(key, data.run);
          return;
        }

        if (event.event === "agent:stream_chunk") {
          if (event.id && Number(event.id) <= snapshotCursor) return;
          void client.cancelQueries({ queryKey: key, exact: true });
          client.setQueryData<RunDetails>(key, (run) => applyStreamChunk(run, event));
          return;
        }

        scheduleRefresh(
          event.event.startsWith("task:") ||
            event.event.startsWith("decision:") ||
            event.event === "plan:ready",
        );
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
      if (refreshTimer !== undefined) clearTimeout(refreshTimer);
      close();
    };
  }, [runId, client, isTerminal, enabled]);

  return {
    query,
    activityEvents: log.data.activityEvents,
    activationOrder: log.data.activationOrder ?? [],
    connectionError: enabled && Boolean(runId) && connectionError === runId,
  };
}

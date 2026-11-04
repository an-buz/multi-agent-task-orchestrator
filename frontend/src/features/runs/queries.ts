"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { isTerminalRun } from "./model";
import { ApiError } from "@/lib/api";

import { deleteRun, getRun, listRuns } from "./api";
import { runQueryKey, runsQueryKey } from "./cache";

export { runQueryKey, runsQueryKey, runEventsQueryKey } from "./cache";

export function useRuns(offset = 0) {
  return useQuery({
    queryKey: [...runsQueryKey, "list", offset],
    queryFn: ({ signal }) => listRuns(signal, offset),
    refetchInterval: (query) =>
      query.state.data?.items.some((run) => !isTerminalRun(run)) ? 5000 : false,
  });
}

export function useRun(id: string | undefined, sseDown = true) {
  return useQuery({
    queryKey: runQueryKey(id),
    queryFn: ({ signal }) => getRun(id!, signal),
    enabled: Boolean(id),
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 3,
    refetchInterval: (query) =>
      query.state.data &&
      !isTerminalRun(query.state.data) &&
      !(query.state.error instanceof ApiError && query.state.error.status === 404) &&
      sseDown
        ? 3000
        : false,
  });
}

export function useDeleteRun() {
  const client = useQueryClient();

  return useMutation({
    mutationFn: deleteRun,
    onSuccess: async (_, id) => {
      await client.cancelQueries({ queryKey: runsQueryKey });

      client.removeQueries({ queryKey: runQueryKey(id) });

      await client.invalidateQueries({ queryKey: [...runsQueryKey, "list"] });
    },
  });
}

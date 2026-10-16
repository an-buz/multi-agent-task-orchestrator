"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteRun, getRun, listRuns } from "./api";

export const runsQueryKey = ["runs"] as const;
export const runQueryKey = (id: string | undefined) => [...runsQueryKey, id] as const;
export const runEventsQueryKey = (id: string | undefined) =>
  [...runQueryKey(id), "events"] as const;

export function useRuns(offset = 0) {
  return useQuery({
    queryKey: [...runsQueryKey, "list", offset],
    queryFn: ({ signal }) => listRuns(signal, offset),
    refetchInterval: 5000,
  });
}

export function useRun(id: string | undefined) {
  return useQuery({
    queryKey: runQueryKey(id),
    queryFn: ({ signal }) => getRun(id!, signal),
    enabled: Boolean(id),
    refetchInterval: 3000,
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

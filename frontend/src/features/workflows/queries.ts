import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiRequest } from "@/lib/api";
import { loadCatalogue } from "@/lib/pagination";

import type { Workflow, WorkflowInput } from "./types";

export const workflowsQueryKey = ["workflows"] as const;

export function useWorkflows() {
  return useQuery({
    queryKey: workflowsQueryKey,
    queryFn: ({ signal }) => loadCatalogue<Workflow>("/workflows", signal),
  });
}

export function useSaveWorkflow() {
  const client = useQueryClient();

  return useMutation({
    mutationFn: ({ id, ...data }: WorkflowInput & { id?: string }) =>
      apiRequest<Workflow>(id ? `/workflows/${id}` : "/workflows", {
        method: id ? "PUT" : "POST",
        body: JSON.stringify(data),
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: workflowsQueryKey }),
  });
}

export function useDeleteWorkflow() {
  const client = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => apiRequest<void>(`/workflows/${id}`, { method: "DELETE" }),
    onSuccess: () => client.invalidateQueries({ queryKey: workflowsQueryKey }),
  });
}

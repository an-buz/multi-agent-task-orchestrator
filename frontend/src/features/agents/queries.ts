import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import { removeItem, upsertItem } from "@/lib/collection";

export const agentsQueryKey = ["agents"] as const;
export const agentModelsQueryKey = ["agent-catalog", "models"] as const;
export const agentToolsQueryKey = ["agent-catalog", "tools"] as const;

import type { Agent, AgentModel, AgentTool } from "./types";

export function useAgents() {
  return useQuery({
    queryKey: agentsQueryKey,
    queryFn: ({ signal }) => apiRequest<{ items: Agent[]; total: number }>("/agents", { signal }),
    staleTime: 30_000,
  });
}

export function useAgentModels() {
  return useQuery({
    queryKey: agentModelsQueryKey,
    queryFn: ({ signal }) => apiRequest<{ items: AgentModel[] }>("/agents/models", { signal }),
    staleTime: 5 * 60_000,
  });
}

export function useAgentCatalog() {
  const models = useAgentModels();
  const tools = useQuery({
    queryKey: agentToolsQueryKey,
    queryFn: ({ signal }) => apiRequest<{ items: AgentTool[] }>("/agents/tools", { signal }),
    staleTime: 5 * 60_000,
  });
  return {
    data:
      models.data && tools.data
        ? { models: models.data.items, tools: tools.data.items }
        : undefined,
    isPending: models.isPending || tools.isPending,
    isLoading: models.isLoading || tools.isLoading,
    isError: models.isError || tools.isError,
    error: models.error ?? tools.error,
    refetch: () => Promise.all([models.refetch(), tools.refetch()]),
  };
}

export function useSaveAgent(id?: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (values: Omit<Agent, "id" | "created_at" | "updated_at">) =>
      apiRequest<Agent>(id ? `/agents/${id}` : "/agents", {
        method: id ? "PUT" : "POST",
        body: JSON.stringify(values),
      }),
    onSuccess: async (agent) => {
      await client.cancelQueries({ queryKey: agentsQueryKey });
      client.setQueryData<{ items: Agent[]; total: number }>(agentsQueryKey, (current) =>
        upsertItem(current, agent),
      );
      await client.invalidateQueries({ queryKey: agentsQueryKey });
    },
  });
}

export function useDeleteAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiRequest<void>(`/agents/${id}`, { method: "DELETE" }),
    onSuccess: async (_result, id) => {
      await queryClient.cancelQueries({ queryKey: agentsQueryKey });
      queryClient.setQueryData<{ items: Agent[]; total: number }>(agentsQueryKey, (current) =>
        removeItem(current, id),
      );
      await queryClient.invalidateQueries({ queryKey: agentsQueryKey });
    },
  });
}

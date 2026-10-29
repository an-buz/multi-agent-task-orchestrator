import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiRequest } from "@/lib/api";
import { agentModelsQueryKey, agentsQueryKey } from "@/features/agents/queries";

import type { AgentModel } from "@/features/agents/types";

import { runsQueryKey } from "@/features/runs/queries";

export interface ManagedModel extends AgentModel {
  enabled: boolean;
}

export interface ModelCatalogue {
  items: ManagedModel[];
}

const modelsQueryKey = ["model-settings"] as const;

export function useModelSettings() {
  return useQuery({
    queryKey: modelsQueryKey,
    queryFn: ({ signal }) => apiRequest<ModelCatalogue>("/settings/models", { signal }),
    refetchInterval: 5000,
  });
}

export function useModelSwitch() {
  const client = useQueryClient();

  return useMutation({
    mutationFn: ({ key, enabled }: { key: string; enabled: boolean }) =>
      apiRequest<ModelCatalogue>(`/settings/models/${encodeURIComponent(key)}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled }),
      }),
    onSuccess: async (catalogue) => {
      await client.cancelQueries({ queryKey: modelsQueryKey });

      client.setQueryData(modelsQueryKey, catalogue);

      await Promise.all([
        client.invalidateQueries({ queryKey: agentModelsQueryKey }),
        client.invalidateQueries({ queryKey: agentsQueryKey }),
        client.invalidateQueries({ queryKey: runsQueryKey }),
      ]);
    },
  });
}

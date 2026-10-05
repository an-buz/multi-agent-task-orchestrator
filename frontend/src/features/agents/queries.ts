import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";

export const agentsQueryKey = ["agents"] as const;
export const agentCatalogQueryKey = ["agent-catalog"] as const;

export interface Agent {
  id: string;
  name: string;
  role: string;
  system_prompt: string;
  model: string;
  temperature: number;
  max_tokens: number;
  context_window: number;
  tools: string[];
  created_at: string;
  updated_at: string;
}

export interface AgentModel {
  key: string;
  provider: "anthropic" | "openai";
  model_id: string;
  tier: "fast" | "balanced" | "powerful";
  context_window: number;
}

export interface AgentTool {
  key: string;
  name: string;
  description: string;
}

export function useAgents() {
  return useQuery({
    queryKey: agentsQueryKey,
    queryFn: () => apiRequest<{ items: Agent[]; total: number }>("/agents"),
    staleTime: 30_000,
  });
}

export function useAgentCatalog() {
  return useQuery({
    queryKey: agentCatalogQueryKey,
    queryFn: async () => {
      const [models, tools] = await Promise.all([
        apiRequest<{ items: AgentModel[] }>("/agents/models"),
        apiRequest<{ items: AgentTool[] }>("/agents/tools"),
      ]);
      return { models: models.items, tools: tools.items };
    },
    staleTime: 5 * 60_000,
  });
}

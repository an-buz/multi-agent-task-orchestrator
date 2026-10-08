import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";

export interface AppConfig {
  default_model: string;
  temperature: number;
  max_tokens: number;
  llm_provider_mode: string;
  code_executor_backend: string;
  anthropic_key_configured: boolean;
  openai_key_configured: boolean;
  tavily_key_configured: boolean;
}

export const configQueryKey = ["settings", "config"] as const;

export function useAppConfig(enabled = true) {
  return useQuery({
    queryKey: configQueryKey,
    queryFn: () => apiRequest<AppConfig>("/settings/config"),
    enabled,
  });
}

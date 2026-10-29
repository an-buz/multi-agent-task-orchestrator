import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiRequest } from "@/lib/api";

import type { AppConfig, SettingsInput } from "./types";

export const configQueryKey = ["settings", "config"] as const;

export function useAppConfig(enabled = true) {
  return useQuery({
    queryKey: configQueryKey,
    queryFn: ({ signal }) => apiRequest<AppConfig>("/settings/config", { signal }),
    enabled,
  });
}

export function useSaveAppConfig() {
  const client = useQueryClient();

  return useMutation({
    mutationFn: (values: SettingsInput) =>
      apiRequest<AppConfig>("/settings/config", {
        method: "PATCH",
        body: JSON.stringify(values),
      }),
    onSuccess: (saved) => client.setQueryData(configQueryKey, saved),
  });
}

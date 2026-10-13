import { useMutation } from "@tanstack/react-query";
import { apiRequest, apiUrl } from "@/lib/api";

import type { ContextFile } from "./types";

export function contextFileDownloadUrl(id: string) {
  return apiUrl(`/files/${encodeURIComponent(id)}/download`);
}

export function useUploadContextFile() {
  return useMutation({
    mutationFn: (file: File) => {
      const body = new FormData();
      body.append("file", file);
      return apiRequest<ContextFile>("/files", { method: "POST", body });
    },
  });
}

export function useDeleteContextFile() {
  return useMutation({
    mutationFn: (id: string) => apiRequest<void>(`/files/${id}`, { method: "DELETE" }),
  });
}

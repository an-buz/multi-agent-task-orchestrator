import { useMutation } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";

export interface ContextFile {
  id: string;
  filename: string;
  media_type: string;
  size_bytes: number;
  created_at: string;
}

export function contextFileDownloadUrl(id: string) {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
  return `${base}/files/${encodeURIComponent(id)}/download`;
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

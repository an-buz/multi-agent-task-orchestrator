import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";

export type WorkflowType = "sequential" | "parallel" | "hybrid";
export interface WorkflowStep {
  step_number: number;
  agent_id: string;
  depends_on: number[];
  input_transform: string;
}
export interface Workflow {
  id: string;
  title: string;
  execution_type: WorkflowType;
  steps: WorkflowStep[];
  graph_layout: Record<string, { x: number; y: number }>;
  created_at: string;
  updated_at: string;
}
export interface WorkflowInput {
  title: string;
  execution_type: WorkflowType;
  steps: WorkflowStep[];
  graph_layout: Record<string, { x: number; y: number }>;
}
export const workflowsQueryKey = ["workflows"] as const;
export function useWorkflows() {
  return useQuery({
    queryKey: workflowsQueryKey,
    queryFn: () => apiRequest<{ items: Workflow[]; total: number }>("/workflows"),
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

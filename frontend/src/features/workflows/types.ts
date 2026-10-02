export type WorkflowMode = "sequential" | "parallel" | "hybrid";

export interface WorkflowSummary {
  id: string;
  name: string;
  mode: WorkflowMode;
  updatedAt: string;
}

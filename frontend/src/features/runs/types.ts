export type RunStatus = "PENDING" | "IN_PROGRESS" | "COMPLETED" | "FAILED" | "CANCELLED";

export interface RunSummary {
  id: string;
  workflowId: string;
  status: RunStatus;
  createdAt: string;
  totalTokens: number;
}

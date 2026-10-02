export type AgentStatus =
  "PENDING" | "IN_PROGRESS" | "COMPLETED" | "FAILED" | "CANCELLED";

export interface AgentSummary {
  id: string;
  name: string;
  role: string;
  model: string;
  status?: AgentStatus;
}

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

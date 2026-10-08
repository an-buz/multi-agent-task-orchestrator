export type RunStatus =
  | "PLANNING"
  | "PENDING"
  | "AWAITING_CONFIRMATION"
  | "IN_PROGRESS"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export interface RunSummary {
  id: string;
  workflow_id: string;
  status: RunStatus;
  created_at: string;
  total_tokens: number;
}

export interface RunStep {
  step_number: number;
  agent_id: string;
  agent_name: string;
  status: RunStatus;
  depends_on: number[];
  input?: string;
  subtask?: string;
  output?: string;
  error?: { code: string; message: string };
  retryable?: boolean;
  prompt_tokens?: number;
  completion_tokens?: number;
  duration_ms?: number;
}

export interface RunPlan {
  summary?: string;
  steps: RunStep[];
}

export interface RunDetails extends RunSummary {
  files?: import("@/features/files/queries").ContextFile[];
  task: string;
  context_text?: string;
  plan?: RunPlan | RunStep[] | null;
  planning_prompt_tokens?: number;
  planning_completion_tokens?: number;
  planning_time_ms?: number;
  planning_error?: { code: string; message: string } | null;
  final_report?: string | null;
  workflow_title?: string;
}

export interface RunListResponse {
  items: RunDetails[];
  total: number;
}
export interface CreateRunInput {
  file_ids?: string[];
  workflow_id: string;
  task: string;
  context_text?: string;
}
export interface CreatedRun {
  id: string;
  status: RunStatus;
}
export interface RunEvent {
  event: string;
  run_id?: string;
  runId?: string;
  timestamp?: string;
  ts?: string;
  payload?: Record<string, unknown>;
  data?: Record<string, unknown>;
}

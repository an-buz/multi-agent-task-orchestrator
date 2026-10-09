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
  model?: string | null;
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
  attempt?: number;
}

export interface RunPlan {
  summary?: string;
  steps: RunStep[];
}

export interface RunDetails extends RunSummary {
  total_time_ms?: number;
  token_budget?: number | null;
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
  token_budget?: number;
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
  id?: string;
  event: string;
  run_id?: string;
  runId?: string;
  timestamp?: string;
  ts?: string;
  payload?: Record<string, unknown>;
  data?: Record<string, unknown>;
}

export interface ToolCallData {
  agentId: string;
  stepNumber: number;
  toolName: string;
  input: { argumentNames: string[] };
}

export interface StreamChunkData {
  agentId: string;
  stepNumber: number;
  textDelta: string;
  output: string;
  reset: boolean;
  attempt: number;
}

export interface ToolResultData {
  agentId: string;
  stepNumber: number;
  toolName: string;
  ok: boolean;
  summary: string;
}

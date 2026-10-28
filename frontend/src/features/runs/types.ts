export type RunStatus =
  | "PLANNING"
  | "PENDING"
  | "AWAITING_CONFIRMATION"
  | "IN_PROGRESS"
  | "PAUSED"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export interface RunSummary {
  id: string;
  workflow_id: string;
  status: RunStatus;
  created_at: string;
  total_tokens: number;
  task: string;
  workflow_title?: string;
  total_time_ms?: number;
}

export interface RunStep {
  step_number: number;
  agent_id: string;
  agent_name: string;
  model?: string | null;
  status: RunStatus;
  depends_on: number[];
  input?: string | null;
  subtask?: string;
  output?: string | null;
  error?: { code: string; message: string } | null;
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
  pause_reasons?: ("MODEL_UNAVAILABLE" | "USER_DECISION_REQUIRED")[];
  decisions?: RunDecision[];
  total_time_ms?: number;
  token_budget?: number | null;
  files?: import("@/features/files/types").ContextFile[];
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

export interface DecisionResolution {
  action: "assign_fixes" | "continue" | "cancel";
  agent_id?: string;
  task?: string;
  comment?: string;
}

export interface RunDecision {
  id: string;
  source_step_number: number;
  status: "PENDING" | "RESOLVED";
  issues: {
    title: string;
    description: string;
    severity: "low" | "medium" | "high" | "critical";
  }[];
  suggested_agent_id: string | null;
  suggested_task: string;
  resolution: DecisionResolution | null;
  created_at: string;
  resolved_at: string | null;
  followup_step_numbers: number[];
}

export interface RunListResponse {
  items: RunSummary[];
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

export interface TaskPausedData {
  taskId: string;
  pauseReasons?: ("MODEL_UNAVAILABLE" | "USER_DECISION_REQUIRED")[];
}

export interface ToolResultData {
  agentId: string;
  stepNumber: number;
  toolName: string;
  ok: boolean;
  summary: string;
}

export interface Agent {
  id: string;
  name: string;
  role: string;
  system_prompt: string;
  model: string;
  temperature: number;
  max_tokens: number;
  context_window: number;
  tools: string[];
  created_at: string;
  updated_at: string;
  available?: boolean;
  requires_reconfiguration?: boolean;
}

export interface AgentModel {
  key: string;
  provider: "anthropic" | "openai" | "gemini";
  model_id: string;
  tier: "fast" | "balanced" | "powerful";
  context_window: number | null;
  max_output_tokens: number | null;
}

export interface AgentTool {
  key: string;
  name: string;
  description: string;
}

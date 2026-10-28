export interface AppConfig {
  default_model: string;
  planner_model: string;
  temperature: number;
  max_tokens: number;
  llm_provider_mode: string;
  code_executor_backend: string;
  anthropic_key_configured: boolean;
  openai_key_configured: boolean;
  gemini_key_configured: boolean;
  tavily_key_configured: boolean;
}

export type SettingsInput = Pick<
  AppConfig,
  "default_model" | "planner_model" | "temperature" | "max_tokens"
>;

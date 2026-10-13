export interface AppConfig {
  default_model: string;
  temperature: number;
  max_tokens: number;
  llm_provider_mode: string;
  code_executor_backend: string;
  anthropic_key_configured: boolean;
  openai_key_configured: boolean;
  tavily_key_configured: boolean;
}

export type SettingsInput = Pick<AppConfig, "default_model" | "temperature" | "max_tokens">;

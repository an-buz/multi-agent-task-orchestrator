import { z } from "zod";

import type { AgentModel } from "./types";

export const agentSchema = z
  .object({
    name: z
      .string()
      .trim()
      .min(1, "Agent name is required.")
      .max(100, "Use 100 characters or fewer."),
    role: z.string().trim().min(1, "Role is required.").max(500, "Use 500 characters or fewer."),
    system_prompt: z.string().trim().min(1, "System prompt is required."),
    model: z.string().min(1),
    temperature: z.number().min(0).max(1),
    max_tokens: z.number().int().min(1),
    context_window: z.number().int().min(1),
    tools: z.array(z.string()),
  })
  .refine((values) => values.max_tokens < values.context_window, {
    path: ["max_tokens"],
    message: "Output tokens must leave room for input in the context window.",
  });

export type AgentFormValues = z.infer<typeof agentSchema>;

export function agentSchemaForModels(models: AgentModel[]) {
  return agentSchema.superRefine((values, context) => {
    const model = models.find((item) => item.key === values.model);

    if (!model) {
      context.addIssue({ code: "custom", path: ["model"], message: "Choose an enabled model." });
      return;
    }

    if (values.max_tokens > model.max_output_tokens) {
      context.addIssue({
        code: "custom",
        path: ["max_tokens"],
        message: `This model supports at most ${model.max_output_tokens.toLocaleString()} output tokens.`,
      });
    }

    if (values.context_window > model.context_window) {
      context.addIssue({
        code: "custom",
        path: ["context_window"],
        message: "Context window exceeds the selected model's limit.",
      });
    }
  });
}

export function modelTokenLimits(values: AgentFormValues, model: AgentModel) {
  const context_window = Math.min(values.context_window, model.context_window);

  return {
    context_window,
    max_tokens: Math.min(values.max_tokens, model.max_output_tokens, context_window - 1),
  };
}

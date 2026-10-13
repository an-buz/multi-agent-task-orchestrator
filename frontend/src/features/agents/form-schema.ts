import { z } from "zod";

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

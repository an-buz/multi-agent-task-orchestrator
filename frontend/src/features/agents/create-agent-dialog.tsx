"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import * as Select from "@radix-ui/react-select";
import { useMutation } from "@tanstack/react-query";
import {
  Bot,
  ChevronDown,
  Code2,
  Database,
  FileText,
  Globe,
  LoaderCircle,
  Plus,
  Sparkles,
  Terminal,
  X,
} from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Slider } from "@/components/ui/slider";
import { apiRequest } from "@/lib/api";

const agentSchema = z.object({
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
});

type AgentFormValues = z.infer<typeof agentSchema>;

const defaultValues: AgentFormValues = {
  name: "",
  role: "",
  system_prompt: "",
  model: "claude-sonnet",
  temperature: 0.7,
  max_tokens: 4096,
  context_window: 128000,
  tools: [],
};

const tools = [
  { id: "code_executor", label: "Code Executor", icon: Code2 },
  { id: "web_search", label: "Web Search", icon: Globe },
  { id: "file_manager", label: "File Manager", icon: FileText },
  { id: "api_caller", label: "API Caller", icon: Globe, restricted: true },
  { id: "database_query", label: "Database Query", icon: Database, restricted: true },
  { id: "terminal_access", label: "Terminal Access", icon: Terminal, restricted: true },
];

const models = [
  { id: "claude-haiku", label: "Claude Haiku", tier: "Fast" },
  { id: "claude-sonnet", label: "Claude Sonnet", tier: "Balanced" },
  { id: "claude-opus", label: "Claude Opus", tier: "Powerful" },
];

export function CreateAgentDialog() {
  const [open, setOpen] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const mutation = useMutation({
    mutationFn: (values: AgentFormValues) =>
      apiRequest<{ id: string }>("/agents", { method: "POST", body: JSON.stringify(values) }),
    onSuccess: () => {
      setOpen(false);
      form.reset(defaultValues);
    },
  });
  const form = useForm<AgentFormValues>({ resolver: zodResolver(agentSchema), defaultValues });
  const temperature = form.watch("temperature");
  const selectedTools = form.watch("tools");
  const selectedModel = form.watch("model");

  function close() {
    setOpen(false);
    form.reset(defaultValues);
    mutation.reset();
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-auto flex items-center justify-center gap-2 rounded-lg border border-dashed border-slate-700 px-3 py-2.5 text-xs text-slate-200 transition hover:border-emerald-500/60 hover:text-emerald-300"
      >
        <Plus size={14} /> Create Agent
      </button>
      {open && (
        <div
          className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-950/80 p-4 backdrop-blur-sm"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) close();
          }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-agent-title"
            onKeyDown={(event) => {
              if (event.key === "Escape") close();
            }}
            className="my-auto w-full max-w-2xl rounded-2xl border border-(--border) bg-(--surface) p-5 shadow-2xl sm:p-7"
          >
            <header className="mb-6 flex items-start justify-between border-b border-(--border) pb-5">
              <div>
                <h2 id="create-agent-title" className="text-lg font-semibold">
                  Create New Agent
                </h2>
                <p className="mt-1 text-xs text-slate-400">
                  Configure your AI agent with a custom role, model, and toolset.
                </p>
              </div>
              <button
                type="button"
                onClick={close}
                aria-label="Close dialog"
                className="rounded-lg p-2 text-slate-400 hover:bg-white/5 hover:text-white"
              >
                <X size={17} />
              </button>
            </header>

            <form
              onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
              className="space-y-5"
            >
              <div className="flex items-center gap-4">
                <span className="grid size-14 shrink-0 place-items-center rounded-full bg-slate-800 text-emerald-400">
                  <Bot size={25} />
                </span>
                <label className="min-w-0 flex-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                  Agent name
                  <input
                    {...form.register("name")}
                    autoFocus
                    placeholder="e.g., Senior Code Reviewer"
                    className="mt-1.5 block w-full rounded-lg border border-(--border) bg-slate-950 px-3 py-2.5 text-base font-normal normal-case tracking-normal text-slate-300 outline-none placeholder:text-slate-500 focus:border-emerald-500"
                  />
                  <span className="mt-1.5 block text-[10px] font-normal normal-case tracking-normal text-slate-500">
                    Choose a unique identifier for this agent in your workflows
                  </span>
                  {form.formState.errors.name && (
                    <span className="mt-1 block text-rose-400">
                      {form.formState.errors.name.message}
                    </span>
                  )}
                </label>
              </div>

              <label className="block text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                Role
                <input
                  {...form.register("role")}
                  placeholder="e.g., Reviews code for bugs, security, and performance"
                  className="mt-1.5 block w-full rounded-lg border border-(--border) bg-slate-950 px-3 py-2.5 text-base font-normal normal-case tracking-normal text-slate-300 outline-none placeholder:text-slate-500 focus:border-emerald-500"
                />
                {form.formState.errors.role && (
                  <span className="mt-1 block normal-case text-rose-400">
                    {form.formState.errors.role.message}
                  </span>
                )}
              </label>

              <label className="block text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                System prompt
                <textarea
                  {...form.register("system_prompt")}
                  rows={4}
                  placeholder="Describe how this agent should behave..."
                  className="mt-1.5 block w-full resize-y rounded-lg border border-(--border) bg-slate-950 p-3 font-mono text-base leading-5 normal-case tracking-normal text-slate-300 outline-none placeholder:text-slate-600 focus:border-emerald-500"
                />
                {form.formState.errors.system_prompt && (
                  <span className="mt-1 block normal-case text-rose-400">
                    {form.formState.errors.system_prompt.message}
                  </span>
                )}
              </label>

              <fieldset>
                <legend className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                  AI model
                </legend>
                <Select.Root
                  value={selectedModel}
                  onValueChange={(model) => form.setValue("model", model)}
                >
                  <Select.Trigger
                    aria-label="AI model"
                    className="flex w-full items-center justify-between rounded-lg border border-(--border) bg-slate-950 py-2.5 pl-3 pr-4 text-base text-slate-300 outline-none focus:border-emerald-500"
                  >
                    <div className="flex flex-row items-center content-center gap-2">
                      <Sparkles size={14} className=" text-emerald-400" />
                      <Select.Value />
                    </div>
                    <Select.Icon>
                      <ChevronDown size={16} className="text-slate-400" />
                    </Select.Icon>
                  </Select.Trigger>
                  <Select.Portal>
                    <Select.Content
                      position="popper"
                      sideOffset={4}
                      className="z-50 max-h-64 min-w-(--radix-select-trigger-width) overflow-hidden rounded-lg border border-(--border) bg-slate-950 p-1 shadow-xl"
                    >
                      <Select.Viewport>
                        {models.map((model) => (
                          <Select.Item
                            key={model.id}
                            value={model.id}
                            className="relative flex cursor-pointer select-none items-center gap-2 rounded-md py-2.5 pl-3 pr-8 text-base text-slate-300 outline-none data-highlighted:bg-white/5 data-highlighted:text-white data-[state=checked]:text-white"
                          >
                            <Sparkles size={14} className="shrink-0 text-emerald-400" />
                            <Select.ItemText>{model.label}</Select.ItemText>
                            <span className="ml-auto text-xs text-slate-500">{model.tier}</span>
                          </Select.Item>
                        ))}
                      </Select.Viewport>
                    </Select.Content>
                  </Select.Portal>
                </Select.Root>
                <div className="mt-2 grid grid-cols-3 gap-2">
                  {(
                    [
                      ["Fast (Haiku)", "claude-haiku"],
                      ["Balanced (Sonnet)", "claude-sonnet"],
                      ["Powerful (Opus)", "claude-opus"],
                    ] as const
                  ).map(([label, model]) => (
                    <button
                      key={label}
                      type="button"
                      onClick={() => form.setValue("model", model)}
                      className={`rounded-md border px-2 py-2 text-xs transition ${form.watch("model") === model ? "border-emerald-500 bg-emerald-500/10 text-emerald-300" : "border-(--border) text-slate-400 hover:border-slate-600"}`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </fieldset>

              <fieldset>
                <legend className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                  Available tools
                </legend>
                <div className="grid gap-2 sm:grid-cols-2">
                  {tools.map(({ id, label, icon: Icon, restricted }) => {
                    const selected = selectedTools.includes(id);
                    return (
                      <button
                        key={id}
                        type="button"
                        role="switch"
                        aria-checked={selected}
                        aria-label={`${label}${restricted ? " (disabled in MVP)" : ""}`}
                        title={
                          restricted ? "This high-risk tool is disabled in the MVP." : undefined
                        }
                        disabled={restricted}
                        onClick={() =>
                          form.setValue(
                            "tools",
                            selected
                              ? selectedTools.filter((tool) => tool !== id)
                              : [...selectedTools, id],
                          )
                        }
                        className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs transition ${selected ? "border-emerald-500/70 bg-emerald-500/10 text-white" : "border-(--border) bg-slate-950 text-slate-400 hover:border-slate-600"} ${restricted ? "cursor-not-allowed opacity-50" : ""}`}
                      >
                        <Icon size={14} className={selected ? "text-emerald-400" : ""} />
                        <span>{label}</span>
                        <span
                          className={`ml-auto flex h-5 w-9 items-center rounded-full p-0.5 transition-colors ${selected ? "bg-emerald-500" : "bg-slate-700"}`}
                        >
                          <span
                            className={`size-4 rounded-full bg-slate-100 shadow transition-transform ${selected ? "translate-x-4" : "translate-x-0"}`}
                          />
                        </span>
                      </button>
                    );
                  })}
                </div>
              </fieldset>

              <div>
                <button
                  type="button"
                  aria-expanded={advanced}
                  onClick={() => setAdvanced(!advanced)}
                  className="flex items-center gap-1 text-xs font-medium text-slate-300 hover:text-white"
                >
                  Advanced Settings{" "}
                  <ChevronDown size={14} className={advanced ? "rotate-180" : ""} />
                </button>
                {advanced && (
                  <div className="mt-4 grid gap-4 sm:grid-cols-3">
                    <label className="text-[10px] text-slate-400">
                      Temperature{" "}
                      <span className="float-right text-emerald-400">{temperature.toFixed(1)}</span>
                      <div className="mt-3">
                        <Slider
                          aria-label="Temperature"
                          min={0}
                          max={1}
                          step={0.1}
                          value={temperature}
                          onValueChange={(value) => form.setValue("temperature", value)}
                        />
                      </div>
                    </label>
                    <label className="text-[10px] text-slate-400">
                      Max tokens
                      <input
                        {...form.register("max_tokens", { valueAsNumber: true })}
                        type="number"
                        min="1"
                        className="mt-2 block w-full rounded-md border border-(--border) bg-slate-950 px-2 py-2 text-base text-slate-300"
                      />
                    </label>
                    <label className="text-[10px] text-slate-400">
                      Context window
                      <span className="relative mt-2 block">
                        <select
                          {...form.register("context_window", { valueAsNumber: true })}
                          className="block w-full appearance-none rounded-md border border-(--border) bg-slate-950 px-2 py-2 pr-9 text-base text-slate-300"
                        >
                          <option value={8000}>8K tokens</option>
                          <option value={32000}>32K tokens</option>
                          <option value={128000}>128K tokens</option>
                          <option value={200000}>200K tokens</option>
                        </select>
                        <ChevronDown
                          size={15}
                          className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400"
                        />
                      </span>
                    </label>
                  </div>
                )}
              </div>

              {mutation.isError && (
                <p role="alert" className="text-xs text-rose-400">
                  {mutation.error.message}. Check that the API is available and try again.
                </p>
              )}
              <footer className="flex justify-end gap-2 border-t border-(--border) pt-5">
                <button
                  type="button"
                  onClick={close}
                  className="rounded-lg border border-(--border) px-4 py-2 text-xs font-medium text-slate-400 hover:bg-white/5"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={mutation.isPending}
                  className="flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-xs font-semibold text-slate-100 transition hover:bg-emerald-400 disabled:cursor-wait disabled:opacity-70"
                >
                  {mutation.isPending ? (
                    <LoaderCircle size={14} className="animate-spin" />
                  ) : (
                    <Sparkles size={14} />
                  )}{" "}
                  Create Agent
                </button>
              </footer>
            </form>
          </section>
        </div>
      )}
    </>
  );
}

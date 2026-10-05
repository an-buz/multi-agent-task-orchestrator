"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import * as Select from "@radix-ui/react-select";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
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
import { useEffect, useState } from "react";
import remarkGfm from "remark-gfm";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Slider } from "@/components/ui/slider";
import { apiRequest } from "@/lib/api";
import { agentsQueryKey, useAgentCatalog, type Agent } from "./queries";

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

const tierLabels = { fast: "Fast", balanced: "Balanced", powerful: "Powerful" } as const;
const modelLabels: Record<string, string> = {
  "claude-haiku": "Claude Haiku",
  "claude-sonnet": "Claude Sonnet",
  "claude-opus": "Claude Opus",
  "gpt-4o": "GPT-4o",
};

const toolIcons = {
  code_executor: Code2,
  web_search: Globe,
  calculator: Database,
  file_reader: FileText,
} as const;

export function CreateAgentDialog({
  agent,
  onClose,
  trigger = true,
}: {
  agent?: Agent;
  onClose?: () => void;
  trigger?: boolean;
}) {
  const queryClient = useQueryClient();
  const catalog = useAgentCatalog();
  const [open, setOpen] = useState(Boolean(agent));
  const [advanced, setAdvanced] = useState(false);
  const [promptView, setPromptView] = useState<"write" | "preview">("write");
  const mutation = useMutation({
    mutationFn: (values: AgentFormValues) =>
      apiRequest<Agent>(agent ? `/agents/${agent.id}` : "/agents", {
        method: agent ? "PUT" : "POST",
        body: JSON.stringify(values),
      }),
    onSuccess: async (savedAgent) => {
      queryClient.setQueryData<{ items: Agent[]; total: number }>(agentsQueryKey, (current) => ({
        items: [savedAgent, ...(current?.items ?? []).filter((item) => item.id !== savedAgent.id)],
        total: current?.total ?? 1,
      }));
      await queryClient.invalidateQueries({ queryKey: agentsQueryKey });
      setOpen(false);
      onClose?.();
      form.reset(defaultValues);
      setPromptView("write");
    },
  });
  const form = useForm<AgentFormValues>({ resolver: zodResolver(agentSchema), defaultValues });
  useEffect(() => {
    if (agent) {
      form.reset({
        name: agent.name,
        role: agent.role,
        system_prompt: agent.system_prompt,
        model: agent.model,
        temperature: agent.temperature,
        max_tokens: agent.max_tokens,
        context_window: agent.context_window,
        tools: agent.tools,
      });
    }
  }, [agent, form]);
  const temperature = form.watch("temperature");
  const selectedTools = form.watch("tools");
  const selectedModel = form.watch("model");
  const models = catalog.data?.models ?? [];
  const tools = catalog.data?.tools ?? [];
  const selectedModelInfo = models.find((model) => model.key === selectedModel);

  function close() {
    setOpen(false);
    form.reset(defaultValues);
    setPromptView("write");
    mutation.reset();
    onClose?.();
  }

  return (
    <>
      {trigger && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="mt-auto flex items-center justify-center gap-2 rounded-lg border border-dashed border-slate-700 px-3 py-2.5 text-xs text-slate-200 transition hover:border-emerald-500/60 hover:text-emerald-300"
        >
          <Plus size={14} /> Create Agent
        </button>
      )}
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
                  {agent ? "Edit Agent" : "Create New Agent"}
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
                <label className="min-w-0 flex-1 tracking-wide text-slate-400">
                  <span className="text-[11px] font-semibold uppercase">Agent name</span>
                  <input
                    {...form.register("name")}
                    autoFocus
                    placeholder="e.g., Senior Code Reviewer"
                    className="mt-1.5 block w-full rounded-lg border border-(--border) bg-slate-950 px-3 py-2.5 text-base font-normal normal-case tracking-normal text-slate-300 outline-none placeholder:text-slate-500 focus:border-emerald-500"
                  />
                  <span className="mt-1.5 block text-[11px] font-normal normal-case tracking-normal text-slate-500">
                    Choose a unique identifier for this agent in your workflows
                  </span>
                  {form.formState.errors.name && (
                    <span className="mt-1 block text-rose-400">
                      {form.formState.errors.name.message}
                    </span>
                  )}
                </label>
              </div>

              <label className="block tracking-wide text-slate-400">
                <span className="text-[11px] font-semibold uppercase">Role</span>
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

              <div className="block tracking-wide text-slate-400">
                <span className="text-[11px] font-semibold uppercase">System prompt</span>
                <div className="mt-1.5 overflow-hidden rounded-lg border border-(--border) bg-slate-950 focus-within:border-emerald-500">
                  <div
                    className="flex border-b border-(--border) px-2 pt-2"
                    role="tablist"
                    aria-label="System prompt view"
                  >
                    {(["write", "preview"] as const).map((view) => (
                      <button
                        key={view}
                        type="button"
                        role="tab"
                        aria-selected={promptView === view}
                        onClick={() => setPromptView(view)}
                        className={`rounded-t-md px-3 py-1.5 text-xs capitalize ${promptView === view ? "border border-b-0 border-(--border) bg-slate-900 text-emerald-300" : "text-slate-500 hover:text-slate-300"}`}
                      >
                        {view}
                      </button>
                    ))}
                  </div>
                  {promptView === "write" ? (
                    <textarea
                      {...form.register("system_prompt")}
                      aria-label="System prompt Markdown source"
                      rows={6}
                      placeholder={
                        "# Role\nDescribe how this agent should behave...\n\n## Guidelines\n- Be concise\n- Explain your reasoning"
                      }
                      className="block w-full resize-y bg-transparent p-3 font-mono text-base leading-6 normal-case tracking-normal text-slate-300 outline-none placeholder:text-slate-600"
                    />
                  ) : (
                    <div
                      role="tabpanel"
                      className="prose prose-invert min-h-36 max-w-none overflow-auto p-3 text-sm prose-headings:text-slate-100 prose-p:text-slate-300 prose-a:text-emerald-300 prose-code:text-emerald-200 prose-pre:bg-slate-900 prose-li:text-slate-300 prose-strong:text-slate-100 prose-th:text-slate-200 prose-td:text-slate-300"
                    >
                      {form.watch("system_prompt").trim() ? (
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {form.watch("system_prompt")}
                        </ReactMarkdown>
                      ) : (
                        <p className="m-0 text-slate-500">Markdown preview will appear here.</p>
                      )}
                    </div>
                  )}
                </div>
                {form.formState.errors.system_prompt && (
                  <span className="mt-1 block normal-case text-rose-400">
                    {form.formState.errors.system_prompt.message}
                  </span>
                )}
              </div>

              <fieldset>
                <legend className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  AI model
                </legend>
                <Select.Root
                  value={selectedModel}
                  onValueChange={(model) => {
                    const modelInfo = models.find((item) => item.key === model);
                    form.setValue("model", model);
                    if (modelInfo) {
                      form.setValue(
                        "context_window",
                        Math.min(form.getValues("context_window"), modelInfo.context_window),
                      );
                      form.setValue(
                        "max_tokens",
                        Math.min(form.getValues("max_tokens"), modelInfo.context_window),
                      );
                    }
                  }}
                  disabled={catalog.isLoading || models.length === 0}
                >
                  <Select.Trigger
                    aria-label="AI model"
                    className="flex w-full items-center justify-between rounded-lg border border-(--border) bg-slate-950 py-2.5 pl-3 pr-4 text-[16px] text-slate-300 outline-none focus:border-emerald-500"
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
                            key={model.key}
                            value={model.key}
                            className="relative flex cursor-pointer select-none items-center gap-2 rounded-md py-2.5 pl-3 pr-8 text-[16px] text-slate-300 outline-none data-highlighted:bg-white/5 data-highlighted:text-white data-[state=checked]:text-white"
                          >
                            <Sparkles size={14} className="shrink-0 text-emerald-400" />
                            <Select.ItemText>{modelLabels[model.key] ?? model.key}</Select.ItemText>
                            <span className="ml-auto text-xs text-slate-500">
                              {tierLabels[model.tier]}
                            </span>
                          </Select.Item>
                        ))}
                      </Select.Viewport>
                    </Select.Content>
                  </Select.Portal>
                </Select.Root>
                {selectedModelInfo && (
                  <p className="mt-2 text-xs text-slate-500">
                    {selectedModelInfo.provider} ·{" "}
                    {selectedModelInfo.context_window.toLocaleString()} token context
                  </p>
                )}
                {catalog.isError && (
                  <p role="alert" className="mt-2 text-xs text-rose-400">
                    Unable to load model catalogue: {catalog.error.message}
                  </p>
                )}
              </fieldset>

              <fieldset>
                <legend className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  Available tools
                </legend>
                <div className="grid gap-2 sm:grid-cols-2">
                  {tools.map((tool) => {
                    const selected = selectedTools.includes(tool.key);
                    const Icon = toolIcons[tool.key as keyof typeof toolIcons] ?? Terminal;
                    return (
                      <button
                        key={tool.key}
                        type="button"
                        role="switch"
                        aria-checked={selected}
                        aria-label={tool.name}
                        title={tool.description}
                        onClick={() =>
                          form.setValue(
                            "tools",
                            selected
                              ? selectedTools.filter((key) => key !== tool.key)
                              : [...selectedTools, tool.key],
                          )
                        }
                        className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs transition ${selected ? "border-emerald-500/70 bg-emerald-500/10 text-white" : "border-(--border) bg-slate-950 text-slate-400 hover:border-slate-600"}`}
                      >
                        <Icon size={14} className={selected ? "text-emerald-400" : ""} />
                        <span>{tool.name}</span>
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
                {catalog.isError && (
                  <p role="alert" className="mt-2 text-xs text-rose-400">
                    Unable to load tool catalogue: {catalog.error.message}
                  </p>
                )}
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
                    <label className="text-[11px] text-slate-400">
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
                    <label className="text-[11px] text-slate-400">
                      Max tokens
                      <input
                        {...form.register("max_tokens", { valueAsNumber: true })}
                        type="number"
                        min="1"
                        className="mt-2 block w-full rounded-md border border-(--border) bg-slate-950 px-2 py-2 text-[16px] text-slate-300"
                      />
                    </label>
                    <label className="text-[11px] text-slate-400">
                      Context window
                      <span className="relative mt-2 block">
                        <select
                          {...form.register("context_window", { valueAsNumber: true })}
                          className="block w-full appearance-none rounded-md border border-(--border) bg-slate-950 px-2 py-2 pr-9 text-[16px] text-slate-300"
                        >
                          <option value={8000}>8K tokens</option>
                          <option value={32000}>32K tokens</option>
                          <option value={128000}>128K tokens</option>
                          <option
                            value={200000}
                            disabled={(selectedModelInfo?.context_window ?? 0) < 200000}
                          >
                            200K tokens
                          </option>
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
                  disabled={
                    mutation.isPending ||
                    catalog.isLoading ||
                    catalog.isError ||
                    models.length === 0
                  }
                  className="flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-xs font-semibold text-slate-100 transition hover:bg-emerald-400 disabled:cursor-wait disabled:opacity-70"
                >
                  {mutation.isPending ? (
                    <LoaderCircle size={14} className="animate-spin" />
                  ) : (
                    <Sparkles size={14} />
                  )}{" "}
                  {agent ? "Save Changes" : "Create Agent"}
                </button>
              </footer>
            </form>
          </section>
        </div>
      )}
    </>
  );
}

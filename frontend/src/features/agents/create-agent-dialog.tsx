"use client";

import { zodResolver } from "@hookform/resolvers/zod";
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
import { useEffect, useId, useState } from "react";
import remarkGfm from "remark-gfm";
import { useForm, useWatch } from "react-hook-form";

import { agentSchemaForModels, modelTokenLimits, type AgentFormValues } from "./form-schema";
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Slider } from "@/components/ui/slider";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectTrigger,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectValue,
} from "@/components/ui/select";

import type { Agent } from "./types";

import { useSaveAgent, useAgentCatalog } from "./queries";
import { useAppConfig } from "@/features/settings/queries";

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
  "gemini-flash": "Gemini Flash",
  "gemini-flash-lite": "Gemini Flash-Lite",
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
  const catalog = useAgentCatalog();

  const [open, setOpen] = useState(Boolean(agent));

  const config = useAppConfig(open && !agent);

  const [advanced, setAdvanced] = useState(false);
  const [promptView, setPromptView] = useState<"write" | "preview">("write");

  const mutation = useSaveAgent(agent?.id);

  const errorId = useId();

  const models = catalog.data?.models ?? [];

  const form = useForm<AgentFormValues>({
    resolver: zodResolver(agentSchemaForModels(models)),
    defaultValues,
  });

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

  useEffect(() => {
    if (open && !agent && config.data) {
      if (!form.getFieldState("model").isDirty) form.setValue("model", config.data.default_model);

      if (!form.getFieldState("temperature").isDirty)
        form.setValue("temperature", config.data.temperature);

      if (!form.getFieldState("max_tokens").isDirty)
        form.setValue("max_tokens", config.data.max_tokens);
    }
  }, [open, agent, config.data, form]);

  const systemPrompt = useWatch({ control: form.control, name: "system_prompt" });
  const contextWindow = useWatch({ control: form.control, name: "context_window" });
  const temperature = useWatch({ control: form.control, name: "temperature" });
  const selectedTools = useWatch({ control: form.control, name: "tools" });
  const selectedModel = useWatch({ control: form.control, name: "model" });

  const tools = catalog.data?.tools ?? [];
  const selectedModelInfo = models.find((model) => model.key === selectedModel);

  function close() {
    if (mutation.isPending) return;

    setOpen(false);
    form.reset(defaultValues);
    setPromptView("write");
    mutation.reset();
    onClose?.();
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (nextOpen) setOpen(true);
        else close();
      }}
    >
      {trigger && (
        <DialogTrigger
          type="button"
          className="mt-auto flex items-center justify-center gap-2 rounded-lg border border-dashed border-slate-700 px-3 py-2.5 text-xs text-foreground transition hover:border-status-completed/60 hover:text-status-completed"
        >
          <Plus size={14} /> Create Agent
        </DialogTrigger>
      )}
      <DialogContent showCloseButton={false} className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <header className="mb-6 flex items-start justify-between border-b border-border pb-5">
          <div>
            <DialogTitle id="create-agent-title">
              {agent ? "Edit Agent" : "Create New Agent"}
            </DialogTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              Configure your AI agent with a custom role, model, and toolset.
            </p>
          </div>
          <button
            type="button"
            onClick={close}
            aria-label="Close dialog"
            className="rounded-lg p-2 text-muted-foreground hover:bg-foreground/5 hover:text-foreground"
          >
            <X size={17} />
          </button>
        </header>

        <form
          noValidate
          onSubmit={form.handleSubmit(
            (values) => {
              if (!models.some((model) => model.key === values.model)) {
                form.setError("model", {
                  message: "Choose an enabled model from a connected provider.",
                });

                return;
              }

              mutation.mutate(values, {
                onSuccess: () => {
                  setOpen(false);
                  onClose?.();
                  form.reset(defaultValues);
                  setPromptView("write");
                },
              });
            },
            (errors) => {
              if (errors.max_tokens || errors.context_window || errors.temperature)
                setAdvanced(true);
            },
          )}
          className="space-y-5"
        >
          <div className="flex items-center gap-4">
            <span className="grid size-14 shrink-0 place-items-center rounded-full bg-secondary text-status-completed">
              <Bot size={25} />
            </span>
            <label className="min-w-0 flex-1 tracking-wide text-muted-foreground">
              <span className="text-[11px] font-semibold uppercase">Agent name</span>
              <Input
                {...form.register("name")}
                autoFocus
                placeholder="e.g., Senior Code Reviewer"
                className="mt-1.5 block w-full rounded-lg border border-border bg-background px-3 py-2.5 text-base font-normal normal-case tracking-normal text-foreground outline-none placeholder:text-muted-foreground focus:border-status-completed"
              />
              <span className="mt-1.5 block text-[11px] font-normal normal-case tracking-normal text-muted-foreground">
                Choose a unique identifier for this agent in your workflows
              </span>
              {form.formState.errors.name && (
                <span className="mt-1 block text-destructive">
                  {form.formState.errors.name.message}
                </span>
              )}
            </label>
          </div>

          <label className="block tracking-wide text-muted-foreground">
            <span className="text-[11px] font-semibold uppercase">Role</span>
            <Input
              {...form.register("role")}
              placeholder="e.g., Reviews code for bugs, security, and performance"
              className="mt-1.5 block w-full rounded-lg border border-border bg-background px-3 py-2.5 text-base font-normal normal-case tracking-normal text-foreground outline-none placeholder:text-muted-foreground focus:border-status-completed"
            />
            {form.formState.errors.role && (
              <span className="mt-1 block normal-case text-destructive">
                {form.formState.errors.role.message}
              </span>
            )}
          </label>

          <div className="block tracking-wide text-muted-foreground">
            <span className="text-[11px] font-semibold uppercase">System prompt</span>
            <div className="mt-1.5 overflow-hidden rounded-lg border border-border bg-background focus-within:border-status-completed">
              <div
                className="flex border-b border-border px-2 pt-2"
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
                    className={`rounded-t-md px-3 py-1.5 text-xs capitalize ${promptView === view ? "border border-b-0 border-border bg-background text-status-completed" : "text-muted-foreground hover:text-foreground"}`}
                  >
                    {view}
                  </button>
                ))}
              </div>
              {promptView === "write" ? (
                <Textarea
                  {...form.register("system_prompt")}
                  aria-label="System prompt Markdown source"
                  rows={6}
                  placeholder={
                    "# Role\nDescribe how this agent should behave...\n\n## Guidelines\n- Be concise\n- Explain your reasoning"
                  }
                  className="block w-full resize-y bg-transparent p-3 font-mono text-base leading-6 normal-case tracking-normal text-foreground outline-none placeholder:text-muted-foreground"
                />
              ) : (
                <div
                  role="tabpanel"
                  className="prose dark:prose-invert min-h-36 max-w-none overflow-auto p-3 text-sm prose-headings:text-foreground prose-p:text-foreground prose-a:text-status-completed prose-code:text-status-completed prose-pre:bg-background prose-li:text-foreground prose-strong:text-foreground prose-th:text-foreground prose-td:text-foreground"
                >
                  {systemPrompt.trim() ? (
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{systemPrompt}</ReactMarkdown>
                  ) : (
                    <p className="m-0 text-muted-foreground">Markdown preview will appear here.</p>
                  )}
                </div>
              )}
            </div>
            {form.formState.errors.system_prompt && (
              <span className="mt-1 block normal-case text-destructive">
                {form.formState.errors.system_prompt.message}
              </span>
            )}
          </div>

          <fieldset>
            <legend className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              AI model
            </legend>
            <Select
              value={selectedModel}
              onValueChange={(model) => {
                if (!model) return;

                const modelInfo = models.find((item) => item.key === model);

                form.setValue("model", model, { shouldDirty: true });

                if (modelInfo) {
                  const limits = modelTokenLimits(form.getValues(), modelInfo);

                  form.setValue("context_window", limits.context_window, { shouldDirty: true });
                  form.setValue("max_tokens", limits.max_tokens, { shouldDirty: true });
                }
              }}
              disabled={catalog.isLoading || models.length === 0}
            >
              <SelectTrigger aria-label="AI model">
                {selectedModelInfo ? (
                  <div className="flex min-w-0 flex-1 items-center gap-2">
                    <Sparkles size={15} className="shrink-0 text-status-completed" />

                    <span className="truncate text-sm text-foreground">
                      {modelLabels[selectedModelInfo.key] ?? selectedModelInfo.key}
                    </span>

                    <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                      {tierLabels[selectedModelInfo.tier as keyof typeof tierLabels]}
                    </span>
                  </div>
                ) : (
                  <SelectValue />
                )}
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {models.map((model) => {
                    const tier = tierLabels[model.tier as keyof typeof tierLabels];

                    return (
                      <SelectItem
                        key={model.key}
                        value={model.key}
                        className="px-3 py-2.5 text-foreground focus:bg-accent focus:text-foreground"
                      >
                        <div className="flex w-full min-w-0 items-center gap-2">
                          <Sparkles size={15} className="shrink-0 text-status-completed" />

                          <span className="min-w-0 flex-1 truncate">
                            {modelLabels[model.key] ?? model.key}
                          </span>

                          <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                            {tier}
                          </span>
                        </div>
                      </SelectItem>
                    );
                  })}
                </SelectGroup>
              </SelectContent>
            </Select>
            {form.formState.errors.model && (
              <p role="alert" className="mt-2 text-xs text-destructive">
                {form.formState.errors.model.message}
              </p>
            )}
            {!selectedModelInfo && !catalog.isPending && (
              <p className="mt-2 text-xs text-muted-foreground">
                {models.length
                  ? "This model is unavailable. Choose an enabled model."
                  : "No enabled models. Enable a model on the Models page first."}
              </p>
            )}
            {selectedModelInfo && (
              <p className="mt-2 text-xs text-muted-foreground">
                {selectedModelInfo.provider} · {selectedModelInfo.context_window.toLocaleString()}{" "}
                token context
              </p>
            )}
            {catalog.isError && (
              <p role="alert" className="mt-2 text-xs text-destructive">
                Unable to load model catalogue: {catalog.error?.message}
              </p>
            )}
          </fieldset>

          <fieldset>
            <legend className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
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
                    className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs transition ${selected ? "border-status-completed/70 bg-status-completed/10 text-foreground" : "border-border bg-background text-muted-foreground hover:border-slate-600"}`}
                  >
                    <Icon size={14} className={selected ? "text-status-completed" : ""} />
                    <span>{tool.name}</span>
                    <span
                      className={`ml-auto flex h-5 w-9 items-center rounded-full p-0.5 transition-colors ${selected ? "bg-status-completed" : "bg-secondary"}`}
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
              <p role="alert" className="mt-2 text-xs text-destructive">
                Unable to load tool catalogue: {catalog.error?.message}
              </p>
            )}
          </fieldset>

          <div>
            <button
              type="button"
              aria-expanded={advanced}
              onClick={() => setAdvanced(!advanced)}
              className="flex items-center gap-1 text-xs font-medium text-foreground hover:text-foreground"
            >
              Advanced Settings <ChevronDown size={14} className={advanced ? "rotate-180" : ""} />
            </button>
            {advanced && (
              <div className="mt-4 grid gap-4 sm:grid-cols-3">
                <label className="text-[11px] text-muted-foreground">
                  Temperature{" "}
                  <span className="float-right text-status-completed">
                    {temperature.toFixed(1)}
                  </span>
                  <div className="mt-3 flex h-5 items-center">
                    <Slider
                      aria-label="Temperature"
                      aria-invalid={Boolean(form.formState.errors.temperature)}
                      aria-describedby={
                        form.formState.errors.temperature ? `${errorId}-temperature` : undefined
                      }
                      min={0}
                      max={1}
                      step={0.1}
                      value={temperature}
                      onValueChange={(value) => {
                        const v = Array.isArray(value) ? value[0] : value;

                        form.setValue("temperature", v, {
                          shouldDirty: true,
                          shouldValidate: form.formState.isSubmitted,
                        });
                      }}
                    />
                  </div>
                  {form.formState.errors.temperature && (
                    <span
                      id={`${errorId}-temperature`}
                      role="alert"
                      className="mt-1 block text-destructive"
                    >
                      {form.formState.errors.temperature.message}
                    </span>
                  )}
                </label>
                <label className="text-[11px] text-muted-foreground">
                  Max tokens
                  <Input
                    {...form.register("max_tokens", { valueAsNumber: true })}
                    type="number"
                    min="1"
                    max={selectedModelInfo?.max_output_tokens}
                    aria-label="Max tokens"
                    aria-invalid={Boolean(form.formState.errors.max_tokens)}
                    aria-describedby={
                      form.formState.errors.max_tokens ? `${errorId}-max-tokens` : undefined
                    }
                    className="mt-2 block w-full rounded-md border border-border bg-background px-2 py-2 text-[16px] text-foreground"
                  />
                  {form.formState.errors.max_tokens && (
                    <span
                      id={`${errorId}-max-tokens`}
                      role="alert"
                      className="mt-1 block text-destructive"
                    >
                      {form.formState.errors.max_tokens.message}
                    </span>
                  )}
                </label>
                <label className="text-[11px] text-muted-foreground">
                  Context window
                  <span className="relative mt-2 block">
                    <Select
                      value={String(contextWindow)}
                      onValueChange={(value) =>
                        value &&
                        form.setValue("context_window", Number(value), {
                          shouldDirty: true,
                          shouldValidate: form.formState.isSubmitted,
                        })
                      }
                    >
                      <SelectTrigger
                        aria-label="Context window"
                        aria-invalid={Boolean(form.formState.errors.context_window)}
                        aria-describedby={
                          form.formState.errors.context_window
                            ? `${errorId}-context-window`
                            : undefined
                        }
                      >
                        <SelectValue>{Number(contextWindow) / 1000}K tokens</SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        <SelectGroup>
                          <SelectItem value="8000">8K tokens</SelectItem>
                          <SelectItem value="32000">32K tokens</SelectItem>
                          <SelectItem value="128000">128K tokens</SelectItem>
                          <SelectItem
                            value="200000"
                            disabled={(selectedModelInfo?.context_window ?? 0) < 200000}
                          >
                            200K tokens
                          </SelectItem>
                        </SelectGroup>
                      </SelectContent>
                    </Select>
                  </span>
                  {form.formState.errors.context_window && (
                    <span
                      id={`${errorId}-context-window`}
                      role="alert"
                      className="mt-1 block text-destructive"
                    >
                      {form.formState.errors.context_window.message}
                    </span>
                  )}
                </label>
              </div>
            )}
          </div>

          {mutation.isError && (
            <p role="alert" className="text-xs text-destructive">
              {mutation.error.message}. Check that the API is available and try again.
            </p>
          )}
          {!agent && config.isError && (
            <p role="alert">Could not load agent defaults. Please reopen the dialog to retry.</p>
          )}
          <footer className="flex justify-end gap-2 border-t border-border pt-5">
            <Button
              variant="secondary"
              type="button"
              onClick={close}
              className="rounded-lg border border-border px-4 py-2 text-xs font-medium text-muted-foreground hover:bg-foreground/5"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={
                mutation.isPending ||
                (!agent && (config.isPending || config.isError)) ||
                catalog.isLoading ||
                catalog.isError ||
                models.length === 0
              }
            >
              {mutation.isPending ? (
                <LoaderCircle size={14} className="animate-spin" />
              ) : (
                <Sparkles size={14} />
              )}{" "}
              {agent ? "Save Changes" : "Create Agent"}
            </Button>
          </footer>
        </form>
      </DialogContent>
    </Dialog>
  );
}

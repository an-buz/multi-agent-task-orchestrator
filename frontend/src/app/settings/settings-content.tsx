"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { LoaderCircle, Settings as SettingsIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Sidebar } from "@/components/sidebar";
import { apiRequest } from "@/lib/api";

const settingsSchema = z.object({
  default_model: z.string().min(1, "Default model is required."),
  temperature: z.number().min(0).max(1),
  max_tokens: z.number().int().min(1).max(8192),
});

type SettingsFormValues = z.infer<typeof settingsSchema>;

interface ModelInfo {
  key: string;
  provider: string;
  model_id: string;
  tier: string;
  context_window: number;
}

interface AppConfig {
  llm_provider_mode: string;
  code_executor_backend: string;
  anthropic_key_configured: boolean;
  openai_key_configured: boolean;
  tavily_key_configured: boolean;
}

export default function SettingsContent() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveNotice, setSaveNotice] = useState("");

  const form = useForm<SettingsFormValues>({
    resolver: zodResolver(settingsSchema),
    defaultValues: { default_model: "", temperature: 0.7, max_tokens: 4096 },
  });

  useEffect(() => {
    let cancelled = false;

    Promise.all([
      apiRequest<AppConfig>("/settings/config"),
      apiRequest<{ items: ModelInfo[] }>("/agents/models").then((res) => res.items),
    ])
      .then(([cfg, mdl]) => {
        if (cancelled) return;
        setConfig(cfg);
        setModels(mdl);

        // Select first model matching the current provider mode.
        const preferredProvider = cfg.llm_provider_mode === "mock" ? "anthropic" : undefined;
        let selectedModel =
          preferredProvider && mdl.find((m) => m.provider === preferredProvider)?.key;
        if (!selectedModel) selectedModel = mdl[0]?.key ?? "";

        form.setValue("default_model", selectedModel);
        setLoadError(null);
      })
      .catch(() => {
        setLoadError("Could not load configuration.");
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onSubmit(values: SettingsFormValues) {
    setSaving(true);
    setSaveNotice("");
    try {
      await apiRequest<AppConfig>("/settings/config", {
        method: "PATCH",
        body: JSON.stringify(values),
      });
      setSaveNotice("Settings saved successfully.");
    } catch (error) {
      setSaveNotice(error instanceof Error ? error.message : "Could not save settings.");
    } finally {
      setSaving(false);
    }
  }

  function handleRetry() {
    setLoadError(null);
    // Re-run the effect by toggling a dummy key; React will re-fetch.
    window.location.reload();
  }

  const saveDisabled = true; // PATCH /settings/config does not persist yet.

  return (
    <main className="min-h-screen lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <Sidebar />
      <section className="min-w-0">
        <header className="flex min-h-20 flex-wrap items-center justify-between gap-3 border-b border-(--border) px-6 py-4 lg:px-8">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
            <p className="mt-1 text-xs text-slate-400">
              API keys, default agent parameters, and system configuration.
            </p>
          </div>
        </header>
        <div className="mx-auto max-w-360 p-6 lg:p-10">
          {/* Load error (distinct from save notice) */}
          {loadError && (
            <div
              role="alert"
              className="mb-5 rounded-lg border border-rose-900/60 bg-rose-950/20 p-4 text-sm text-rose-300"
            >
              {loadError}{" "}
              <button onClick={handleRetry} className="underline">
                Retry
              </button>
            </div>
          )}

          {/* Loading state */}
          {!config && !loadError && (
            <div className="grid min-h-72 place-items-center rounded-xl border border-dashed border-(--border) bg-(--surface) p-8 text-center">
              <div>
                <LoaderCircle size={24} className="mx-auto animate-spin text-slate-400" />
                <h2 className="mt-4 font-semibold">Loading settings…</h2>
                <p className="mt-2 text-sm text-slate-400">
                  Loading configuration and model catalog from the server.
                </p>
              </div>
            </div>
          )}

          {/* Loaded config */}
          {config && !loadError && (
            <section className="space-y-6">
              {/* API Keys Section */}
              <article className="rounded-xl border border-(--border) bg-(--surface) p-5">
                <h2 className="text-sm font-semibold">API keys</h2>
                <p className="mt-1 text-xs text-slate-400">
                  API keys are configured on the server side. Keys must be set in environment
                  variables and never committed to version control.
                </p>
                <dl className="mt-5 grid gap-x-6 gap-y-3 sm:grid-cols-2">
                  <ApiKeyStatus label="Anthropic" configured={config.anthropic_key_configured} />
                  <ApiKeyStatus label="OpenAI" configured={config.openai_key_configured} />
                  <ApiKeyStatus label="Tavily" configured={config.tavily_key_configured} />
                </dl>
              </article>

              {/* LLM Provider Mode */}
              <article className="rounded-xl border border-(--border) bg-(--surface) p-5">
                <h2 className="text-sm font-semibold">LLM provider mode</h2>
                <p className="mt-1 text-xs text-slate-400">
                  When set to{" "}
                  <span className="font-mono text-emerald-300">{config.llm_provider_mode}</span>,
                  the orchestrator uses{" "}
                  {config.llm_provider_mode === "mock"
                    ? "deterministic mock responses"
                    : "real model APIs"}
                  .
                </p>
              </article>

              {/* Code Executor */}
              <article className="rounded-xl border border-(--border) bg-(--surface) p-5">
                <h2 className="text-sm font-semibold">Code executor</h2>
                <p className="mt-1 text-xs text-slate-400">
                  The code executor backend is{" "}
                  <span className="font-mono text-emerald-300">{config.code_executor_backend}</span>
                  .
                </p>
              </article>

              {/* Save notice (distinct from load error) */}
              {(saveNotice || loadError) && (
                <div
                  role="alert"
                  className={`rounded-lg border p-4 text-sm ${
                    saveNotice.startsWith("Settings saved")
                      ? "border-emerald-900/60 bg-emerald-950/20 text-emerald-300"
                      : saveNotice
                        ? "border-rose-900/60 bg-rose-950/20 text-rose-300"
                        : ""
                  }`}
                >
                  {saveNotice}
                </div>
              )}

              {/* Default Agent Parameters */}
              <article className="rounded-xl border border-(--border) bg-(--surface) p-5">
                <h2 className="text-sm font-semibold">Default agent parameters</h2>
                <p className="mt-1 text-xs text-slate-400">
                  Values applied when creating a new agent. Adjusted values can be overridden in the
                  agent creation form. Saving requires a backend endpoint that persists these
                  settings; it is not yet available.
                </p>

                <form onSubmit={form.handleSubmit(onSubmit)} className="mt-5 space-y-5">
                  <label className="block text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                    Default model
                    <div id="model-error" aria-live="polite" />
                    <select
                      {...form.register("default_model")}
                      disabled={saveDisabled}
                      className={`mt-2 block w-full rounded-lg border px-3 py-2.5 text-sm outline-none focus:border-emerald-500 ${form.formState.errors.default_model ? "border-rose-500" : "border-(--border)"}`}
                    >
                      {models.map((model) => (
                        <option key={model.key} value={model.key}>
                          {formatModelLabel(model)} ({model.tier}, {model.provider})
                        </option>
                      ))}
                    </select>
                    {form.formState.errors.default_model && (
                      <p className="mt-1.5 text-xs text-rose-400" aria-hidden="false">
                        {form.formState.errors.default_model.message}
                      </p>
                    )}
                  </label>

                  <div className="grid gap-5 sm:grid-cols-2">
                    <label className="block text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      Default temperature (0.0–1.0)
                      <input
                        {...form.register("temperature", { valueAsNumber: true })}
                        type="number"
                        step={0.1}
                        min={0}
                        max={1}
                        aria-describedby="temp-error"
                        disabled={saveDisabled}
                        className={`mt-2 block w-full rounded-lg border px-3 py-2.5 text-sm outline-none focus:border-emerald-500 ${form.formState.errors.temperature ? "border-rose-500" : "border-(--border)"}`}
                      />
                      {form.formState.errors.temperature && (
                        <p id="temp-error" className="mt-1.5 text-xs text-rose-400">
                          {form.formState.errors.temperature.message}
                        </p>
                      )}
                    </label>

                    <label className="block text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      Default max tokens (1–8192)
                      <input
                        {...form.register("max_tokens", { valueAsNumber: true })}
                        type="number"
                        min={1}
                        max={8192}
                        aria-describedby="tokens-error"
                        disabled={saveDisabled}
                        className={`mt-2 block w-full rounded-lg border px-3 py-2.5 text-sm outline-none focus:border-emerald-500 ${form.formState.errors.max_tokens ? "border-rose-500" : "border-(--border)"}`}
                      />
                      {form.formState.errors.max_tokens && (
                        <p id="tokens-error" className="mt-1.5 text-xs text-rose-400">
                          {form.formState.errors.max_tokens.message}
                        </p>
                      )}
                    </label>
                  </div>

                  <footer className="flex justify-end gap-2">
                    <button
                      type="submit"
                      disabled={saveDisabled || saving || form.formState.isSubmitting}
                      className="flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2.5 text-sm font-semibold text-slate-950 disabled:opacity-50"
                    >
                      {saving ? (
                        <LoaderCircle size={15} className="animate-spin" />
                      ) : saveDisabled ? (
                        "Not yet available"
                      ) : (
                        <>
                          <SettingsIcon size={15} /> Save changes
                        </>
                      )}
                    </button>
                  </footer>
                </form>
              </article>
            </section>
          )}
        </div>
      </section>
    </main>
  );
}

function formatModelLabel(model: ModelInfo): string {
  const parts = model.key.split("-");
  return `${parts[0].charAt(0).toUpperCase() + parts[0].slice(1)} ${parts
    .slice(1)
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(" ")}`;
}

function ApiKeyStatus({ label, configured }: { label: string; configured: boolean }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-(--border) px-4 py-2.5">
      <span
        className={`size-2 shrink-0 rounded-full ${configured ? "bg-emerald-400" : "bg-slate-600"}`}
      />
      <div>
        <dt className="text-xs font-medium text-slate-300">{label}</dt>
        <dd className={`text-[11px] ${configured ? "text-emerald-400" : "text-slate-500"}`}>
          {configured ? "Configured" : "Not configured"}
        </dd>
      </div>
    </div>
  );
}

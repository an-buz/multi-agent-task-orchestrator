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

const defaultValues: SettingsFormValues = {
  default_model: "claude-sonnet",
  temperature: 0.7,
  max_tokens: 4096,
};

interface AppConfig {
  llm_provider_mode: string;
  code_executor_backend: string;
  anthropic_key_configured: boolean;
  openai_key_configured: boolean;
  tavily_key_configured: boolean;
}

export default function SettingsContent() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");

  const form = useForm<SettingsFormValues>({
    resolver: zodResolver(settingsSchema),
    defaultValues,
  });

  useEffect(() => {
    apiRequest<AppConfig>("/settings/config")
      .then((data) => {
        setConfig(data);
      })
      .catch(() => {
        setNotice("Could not load configuration.");
      })
      .finally(() => setLoading(false));
  }, []);

  async function onSubmit(values: SettingsFormValues) {
    setSaving(true);
    setNotice("");
    try {
      await apiRequest<AppConfig>("/settings/config", {
        method: "PATCH",
        body: JSON.stringify(values),
      });
      setNotice("Settings saved successfully.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not save settings.");
    } finally {
      setSaving(false);
    }
  }

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
          {loading && (
            <div className="grid min-h-52 place-items-center text-sm text-slate-400">
              <LoaderCircle className="animate-spin" size={20} />
            </div>
          )}

          {!loading && config && (
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
                  <span className="font-mono text-emerald-300">{config.llm_provider_mode}</span>,{" "}
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
                  The code executor runs agent code in an isolated Docker container when enabled.{" "}
                  <span className="font-mono text-emerald-300">{config.code_executor_backend}</span>
                  .
                </p>
              </article>

              {/* Default Agent Parameters */}
              {notice && (
                <div
                  role="alert"
                  className={`rounded-lg border p-4 text-sm ${saving ? "border-slate-700 text-slate-300" : config ? "" : "text-rose-300"}`}
                >
                  {notice}
                </div>
              )}

              <article className="rounded-xl border border-(--border) bg-(--surface) p-5">
                <h2 className="text-sm font-semibold">Default agent parameters</h2>
                <p className="mt-1 text-xs text-slate-400">
                  Values applied when creating a new agent. Adjusted values can be overridden in the
                  agent creation form.
                </p>

                <form onSubmit={form.handleSubmit(onSubmit)} className="mt-5 space-y-5">
                  <label className="block text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                    Default model
                    <select
                      {...form.register("default_model")}
                      className="mt-2 block w-full rounded-lg border border-(--border) bg-slate-950 px-3 py-2.5 text-sm outline-none focus:border-emerald-500"
                    >
                      <option value="claude-sonnet">Claude Sonnet</option>
                      <option value="claude-haiku">Claude Haiku</option>
                      <option value="claude-opus">Claude Opus</option>
                      <option value="gpt-4o">GPT-4o</option>
                    </select>
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
                        className="mt-2 block w-full rounded-lg border border-(--border) bg-slate-950 px-3 py-2.5 text-sm outline-none focus:border-emerald-500"
                      />
                    </label>

                    <label className="block text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      Default max tokens (1–8192)
                      <input
                        {...form.register("max_tokens", { valueAsNumber: true })}
                        type="number"
                        min={1}
                        max={8192}
                        className="mt-2 block w-full rounded-lg border border-(--border) bg-slate-950 px-3 py-2.5 text-sm outline-none focus:border-emerald-500"
                      />
                    </label>
                  </div>

                  <footer className="flex justify-end gap-2">
                    <button
                      type="submit"
                      disabled={saving || form.formState.isSubmitting}
                      className="flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2.5 text-sm font-semibold text-slate-950 disabled:opacity-50"
                    >
                      {saving ? (
                        <LoaderCircle size={15} className="animate-spin" />
                      ) : (
                        <SettingsIcon size={15} />
                      )}{" "}
                      Save changes
                    </button>
                  </footer>
                </form>

                {form.formState.errors.default_model && (
                  <p className="mt-2 text-xs text-rose-400">
                    {form.formState.errors.default_model.message}
                  </p>
                )}
              </article>
            </section>
          )}
        </div>
      </section>
    </main>
  );
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

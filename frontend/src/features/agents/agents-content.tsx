"use client";

import { useMemo, useState } from "react";
import {
  Bot,
  CalendarDays,
  Code2,
  Database,
  FileText,
  Globe,
  LoaderCircle,
  Pencil,
  Search,
  Trash2,
  X,
  Info,
} from "lucide-react";

import {
  Select,
  SelectTrigger,
  SelectContent,
  SelectGroup,
  SelectItem,
} from "@/components/ui/select";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/status-badge";
import { DeleteConfirmationDialog } from "@/components/delete-confirmation-dialog";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { CreateAgentDialog } from "@/features/agents/create-agent-dialog";

import type { Agent } from "./types";

import { useAgents, useDeleteAgent } from "@/features/agents/queries";

const toolIcons: Record<string, typeof Globe> = {
  web_search: Globe,
  code_executor: Code2,
  calculator: Database,
  file_reader: FileText,
};

export default function AgentsContent() {
  const agentsQuery = useAgents();

  const deleteMutation = useDeleteAgent();

  const [search, setSearch] = useState("");
  const [modelFilter, setModelFilter] = useState("all");
  const [selected, setSelected] = useState<Agent | null>(null);
  const [editing, setEditing] = useState<Agent | null>(null);
  const [deleting, setDeleting] = useState<Agent | null>(null);

  const agents = useMemo(() => agentsQuery.data?.items ?? [], [agentsQuery.data?.items]);
  const models = useMemo(() => [...new Set(agents.map((agent) => agent.model))].sort(), [agents]);

  const filtered = agents.filter((agent) => {
    const term = search.trim().toLowerCase();
    const matchesSearch =
      !term ||
      [agent.name, agent.role, agent.model].some((value) => value.toLowerCase().includes(term));

    return matchesSearch && (modelFilter === "all" || agent.model === modelFilter);
  });

  async function removeAgent(agent: Agent) {
    await deleteMutation.mutateAsync(agent.id);

    if (selected?.id === agent.id) setSelected(null);
  }

  return (
    <AppShell>
      <section className="min-w-0">
        <header className="flex min-h-20 flex-wrap items-center justify-between gap-3 border-b border-border px-6 py-4 lg:px-8">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Agents</h1>
            <p className="mt-1 text-xs text-muted-foreground">
              Team workspace · Browse and manage the agents available to your workflows.
            </p>
          </div>
        </header>
        <div className="mx-auto max-w-360 p-6 lg:p-10">
          <CreateAgentDialog trigger={false} />

          <section className="mb-6 rounded-xl border border-border bg-card p-4">
            <div className="grid gap-3 md:grid-cols-[1fr_220px]">
              <label className="relative block">
                <Search
                  size={16}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                />
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search agents by name, role, or model…"
                  className="w-full rounded-lg border border-border bg-background py-2.5 pl-9 pr-3 text-sm outline-none focus:border-status-completed"
                />
              </label>
              <Select value={modelFilter} onValueChange={(value) => setModelFilter(value ?? "all")}>
                <SelectTrigger aria-label="Filter by model" className="h-10">
                  {modelFilter === "all" ? "All models" : modelFilter}
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="all">All models</SelectItem>
                    {models.map((model) => (
                      <SelectItem key={model} value={model}>
                        {model}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>
          </section>

          {agentsQuery.isLoading && (
            <div className="grid min-h-52 place-items-center text-sm text-muted-foreground">
              <LoaderCircle className="animate-spin" size={20} />
            </div>
          )}
          {agentsQuery.isError && (
            <div
              className="rounded-xl border border-destructive/60 bg-destructive/20 p-5 text-sm text-destructive"
              role="alert"
            >
              Could not load agents.{" "}
              <Button
                onClick={() => void agentsQuery.refetch()}
                variant="ghost"
                className="underline"
              >
                Try again
              </Button>
            </div>
          )}
          {deleteMutation.isError && (
            <p role="alert" className="mb-4 text-sm text-destructive">
              {deleteMutation.error.message}
            </p>
          )}
          {!agentsQuery.isLoading && !agentsQuery.isError && filtered.length === 0 && (
            <div className="grid min-h-72 place-items-center rounded-xl border border-dashed border-border bg-card p-8 text-center">
              <div>
                <span className="mx-auto grid size-12 place-items-center rounded-xl bg-status-completed/10 text-status-completed">
                  <Bot size={22} />
                </span>
                <h2 className="mt-4 text-base font-semibold">
                  {agents.length === 0 ? "No agents yet" : "No matching agents"}
                </h2>
                <p className="mt-2 max-w-sm text-sm text-muted-foreground">
                  {agents.length === 0
                    ? "Create your first agent to make it available in workflows."
                    : "Try a different search or model filter."}
                </p>
              </div>
            </div>
          )}
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {filtered.map((agent) => (
              <article
                key={agent.id}
                className="flex min-h-64 flex-col rounded-xl border border-border bg-card p-5 transition hover:border-slate-600"
              >
                <span className="flex w-full items-start gap-3 text-left">
                  <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-status-completed/10 text-status-completed">
                    <Bot size={21} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold">{agent.name}</span>
                    <span className="mt-1 block truncate font-mono text-[11px] text-muted-foreground">
                      {agent.model}
                    </span>
                  </span>
                </span>
                {agent.available === false && (
                  <div className="mt-3 flex flex-col gap-2">
                    <StatusBadge status="UNAVAILABLE" />
                    <p className="text-xs text-muted-foreground">
                      Choose an enabled model and save this agent to resume its runs.
                    </p>
                  </div>
                )}
                <p className="mt-4 line-clamp-3 min-h-14 text-sm leading-6 text-muted-foreground">
                  {agent.role}
                </p>
                <div className="mt-4 flex items-center gap-2 border-t border-border pt-3 text-muted-foreground">
                  <div
                    className="flex min-w-0 flex-1 items-center gap-2"
                    aria-label="Enabled tools"
                  >
                    {agent.tools.map((tool) => {
                      const Icon = toolIcons[tool] ?? Bot;

                      return (
                        <span key={tool} title={tool} className="rounded-md bg-foreground/5 p-1.5">
                          <Icon size={14} />
                        </span>
                      );
                    })}
                    {agent.tools.length === 0 && (
                      <span className="text-[11px]">No tools enabled</span>
                    )}
                  </div>
                  <span
                    title={new Date(agent.created_at).toLocaleDateString()}
                    className="flex items-center gap-1 text-[11px]"
                  >
                    <CalendarDays size={13} />
                    {new Date(agent.created_at).toLocaleDateString()}
                  </span>
                </div>
                <footer className="mt-auto flex justify-end gap-2 pt-4">
                  <Button onClick={() => setSelected(agent)} size="icon">
                    <Info size={20} />
                  </Button>
                  <Button
                    onClick={() => setEditing(agent)}
                    aria-label={`Edit ${agent.name}`}
                    size="icon"
                  >
                    <Pencil size={18} />
                  </Button>
                  <Button
                    onClick={() => {
                      deleteMutation.reset();
                      setDeleting(agent);
                    }}
                    disabled={deleteMutation.isPending}
                    aria-label={`Delete ${agent.name}`}
                    size="icon"
                    variant="destructive"
                  >
                    <Trash2 size={18} />
                  </Button>
                </footer>
              </article>
            ))}
          </div>
          <p className="mt-5 text-xs text-muted-foreground">
            Showing {filtered.length} of {agentsQuery.data?.total ?? agents.length} agents
          </p>
        </div>
      </section>

      <Dialog
        open={Boolean(selected)}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
      >
        {selected && (
          <DialogContent
            showCloseButton={false}
            className="top-0 right-0 left-auto h-screen translate-x-0 translate-y-0 overflow-y-auto rounded-none sm:max-w-lg"
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs uppercase tracking-widest text-status-completed">
                  Agent details
                </p>
                <DialogTitle id="agent-details-title">{selected.name}</DialogTitle>
              </div>
              <Button
                onClick={() => setSelected(null)}
                aria-label="Close details"
                variant="ghost"
                size="icon-sm"
              >
                <X />
              </Button>
            </div>
            <dl className="mt-8 space-y-5 text-sm">
              <Detail label="Role" value={selected.role} />
              <Detail label="Model" value={selected.model} />
              <Detail label="System prompt" value={selected.system_prompt} />
              <Detail label="Temperature" value={String(selected.temperature)} />
              <Detail label="Max tokens" value={selected.max_tokens.toLocaleString()} />
              <Detail
                label="Context window"
                value={`${selected.context_window.toLocaleString()} tokens`}
              />
              <Detail
                label="Tools"
                value={selected.tools.length ? selected.tools.join(", ") : "None"}
              />
              <Detail label="Created" value={new Date(selected.created_at).toLocaleString()} />
              <Detail label="Updated" value={new Date(selected.updated_at).toLocaleString()} />
            </dl>
            <Button
              onClick={() => {
                setEditing(selected);
                setSelected(null);
              }}
              className="mt-8 flex items-center gap-2 rounded-lg bg-status-completed px-4 py-2.5 text-sm font-semibold text-foreground"
            >
              <Pencil size={15} /> Edit agent
            </Button>
          </DialogContent>
        )}
      </Dialog>
      {editing && (
        <CreateAgentDialog key={editing.id} agent={editing} onClose={() => setEditing(null)} />
      )}
      {deleting && (
        <DeleteConfirmationDialog
          key={deleting.id}
          name={deleting.name}
          entity="agent"
          pending={deleteMutation.isPending}
          onClose={() => setDeleting(null)}
          onConfirm={() => removeAgent(deleting)}
        />
      )}
    </AppShell>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-1 whitespace-pre-wrap wrap-break-words leading-6 text-foreground">
        {value}
      </dd>
    </div>
  );
}

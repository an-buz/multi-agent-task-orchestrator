"use client";

import { Activity, Bot, Cpu, GitBranch, LayoutGrid, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { CreateAgentDialog } from "@/features/agents/create-agent-dialog";
import { useAgents } from "@/features/agents/queries";

export function Sidebar() {
  const pathname = usePathname();
  const agentsQuery = useAgents();
  const agents = (agentsQuery.data?.items ?? []).filter((agent) => agent.available !== false);

  return (
    <aside className="flex flex-col border-b border-border bg-card p-5 lg:min-h-screen lg:border-b-0 lg:border-r">
      <Link className="mb-7 flex items-center gap-3" href="/">
        <span className="grid size-8 place-items-center rounded-md border bg-status-completed/15 text-status-completed">
          <Cpu size={19} />
        </span>
        <span className="block text-lg font-bold tracking-wide">AgentFlow</span>
        <span className="rounded-sm bg-secondary px-2 py-px font-mono text-xs text-muted-foreground">
          v0.1
        </span>
      </Link>
      <nav className="space-y-0.5 text-sm">
        <Link
          className={`flex items-center gap-3 rounded-lg px-3 py-2.5 font-medium ${pathname === "/" ? "bg-status-completed/10 text-status-completed" : "text-muted-foreground hover:bg-foreground/5 hover:text-foreground"}`}
          href="/"
        >
          <LayoutGrid size={16} /> Dashboard
        </Link>
        <Link
          className={`flex items-center gap-3 rounded-lg px-3 py-2.5 ${pathname.startsWith("/workflows") ? "bg-status-completed/10 font-medium text-status-completed" : "text-muted-foreground hover:bg-foreground/5 hover:text-foreground"}`}
          href="/workflows"
        >
          <GitBranch size={16} /> Workflows
        </Link>
        <Link
          className={`flex items-center gap-3 rounded-lg px-3 py-2.5 ${pathname.startsWith("/agents") ? "bg-status-completed/10 font-medium text-status-completed" : "text-muted-foreground hover:bg-foreground/5 hover:text-foreground"}`}
          href="/agents"
        >
          <Bot size={16} /> Agents
        </Link>
        <Link
          className={`flex items-center gap-3 rounded-lg px-3 py-2.5 ${pathname.startsWith("/runs") ? "bg-status-completed/10 font-medium text-status-completed" : "text-muted-foreground hover:bg-foreground/5 hover:text-foreground"}`}
          href="/runs"
        >
          <Activity size={16} /> Runs
        </Link>
        <Link
          href="/models"
          aria-current={pathname === "/models" ? "page" : undefined}
          className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-muted-foreground hover:bg-accent hover:text-foreground aria-[current=page]:bg-accent aria-[current=page]:text-foreground"
        >
          <Cpu size={16} /> Models
        </Link>
        <Link
          className={`flex items-center gap-3 rounded-lg px-3 py-2.5 ${pathname === "/settings" ? "bg-status-completed/10 font-medium text-status-completed" : "text-muted-foreground hover:bg-foreground/5 hover:text-foreground"}`}
          href="/settings"
        >
          <Settings size={16} /> Settings
        </Link>
      </nav>
      <div className="mb-6 mt-8 border-t border-border" />
      <div className="flex items-center justify-between">
        <p className="text-[11px] font-semibold uppercase tracking-[.18em] text-foreground">
          Ready agents
        </p>
        <span className="rounded-md bg-foreground/5 px-2 py-0.5 text-xs text-muted-foreground">
          {agents.length}
        </span>
      </div>
      <div className="mt-3 space-y-2">
        {agents.map((agent) => (
          <div
            key={agent.id}
            className="flex items-center gap-3 rounded-lg bg-secondary px-3 py-2.5"
          >
            <span className="grid size-8 shrink-0 place-items-center rounded-full bg-foreground/5 text-xs font-semibold text-foreground">
              {agent.name.charAt(0)}
            </span>
            <span className="min-w-0 leading-tight">
              <span className="block truncate text-xs font-medium">{agent.name}</span>
              <span className="mt-0.5 block truncate font-mono text-[10px] text-muted-foreground">
                {agent.model}
              </span>
            </span>
            <span className="ml-auto size-1.5 rounded-full bg-status-completed" />
          </div>
        ))}
        {agentsQuery.isLoading && (
          <p className="px-3 py-2 text-xs text-muted-foreground">Loading agents…</p>
        )}
        {agentsQuery.isError && (
          <p role="alert" className="px-3 py-2 text-xs text-destructive">
            Could not load agents.
          </p>
        )}
        {!agentsQuery.isLoading && !agentsQuery.isError && agents.length === 0 && (
          <p className="px-3 py-2 text-xs text-muted-foreground">
            {agentsQuery.data?.items.length ? "No available agents." : "No agents yet."}
          </p>
        )}
      </div>
      <CreateAgentDialog />
    </aside>
  );
}

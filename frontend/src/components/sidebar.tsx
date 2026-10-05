"use client";

import { Bot, Box, Cpu, GitBranch, LayoutGrid, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { CreateAgentDialog } from "@/features/agents/create-agent-dialog";
import { useAgents } from "@/features/agents/queries";

export function Sidebar() {
  const pathname = usePathname();
  const agentsQuery = useAgents();
  const agents = agentsQuery.data?.items ?? [];

  return (
    <aside className="flex flex-col border-b border-(--border) bg-(--surface) p-5 lg:min-h-screen lg:border-b-0 lg:border-r">
      <Link className="mb-7 flex items-center gap-3" href="/">
        <span className="grid size-8 place-items-center rounded-md border bg-emerald-500/15 text-emerald-400">
          <Cpu size={19} />
        </span>
        <span className="block text-lg font-bold tracking-wide">AgentFlow</span>
        <span className="rounded-sm bg-slate-700 px-2 py-px font-mono text-xs text-(--muted)">
          v0.1
        </span>
      </Link>
      <nav className="space-y-0.5 text-sm">
        <Link
          className={`flex items-center gap-3 rounded-lg px-3 py-2.5 font-medium ${pathname === "/" ? "bg-emerald-500/10 text-emerald-300" : "text-slate-400 hover:bg-white/5 hover:text-white"}`}
          href="/"
        >
          <LayoutGrid size={16} /> Dashboard
        </Link>
        <Link
          className={`flex items-center gap-3 rounded-lg px-3 py-2.5 ${pathname.startsWith("/workflows") ? "bg-emerald-500/10 font-medium text-emerald-300" : "text-slate-400 hover:bg-white/5 hover:text-white"}`}
          href="/workflows"
        >
          <GitBranch size={16} /> Workflows
        </Link>
        <Link
          className={`flex items-center gap-3 rounded-lg px-3 py-2.5 ${pathname.startsWith("/agents") ? "bg-emerald-500/10 font-medium text-emerald-300" : "text-slate-400 hover:bg-white/5 hover:text-white"}`}
          href="/agents"
        >
          <Bot size={16} /> Agents
        </Link>
        <Link
          className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-slate-400 hover:bg-white/5 hover:text-white"
          href="/settings"
        >
          <Box size={16} /> Models
        </Link>
        <Link
          className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-slate-400 hover:bg-white/5 hover:text-white"
          href="/settings"
        >
          <Settings size={16} /> Settings
        </Link>
      </nav>
      <div className="mb-6 mt-8 border-t border-(--border)" />
      <div className="flex items-center justify-between">
        <p className="text-[11px] font-semibold uppercase tracking-[.18em] text-slate-300">
          Ready agents
        </p>
        <span className="rounded-md bg-white/5 px-2 py-0.5 text-xs text-slate-400">
          {agentsQuery.data?.total ?? agents.length}
        </span>
      </div>
      <div className="mt-3 space-y-2">
        {agents.map((agent) => (
          <div
            key={agent.name}
            className="flex items-center gap-3 rounded-lg bg-[#0f172a] px-3 py-2.5"
          >
            <span className="grid size-8 shrink-0 place-items-center rounded-full bg-white/5 text-xs font-semibold text-slate-300">
              {agent.name.charAt(0)}
            </span>
            <span className="min-w-0 leading-tight">
              <span className="block truncate text-xs font-medium">{agent.name}</span>
              <span className="mt-0.5 block truncate font-mono text-[10px] text-slate-500">
                {agent.model}
              </span>
            </span>
            <span className="ml-auto size-1.5 rounded-full bg-emerald-400" />
          </div>
        ))}
        {agentsQuery.isLoading && (
          <p className="px-3 py-2 text-xs text-slate-500">Loading agents…</p>
        )}
        {agentsQuery.isError && (
          <p role="alert" className="px-3 py-2 text-xs text-rose-400">
            Could not load agents.
          </p>
        )}
        {!agentsQuery.isLoading && !agentsQuery.isError && agents.length === 0 && (
          <p className="px-3 py-2 text-xs text-slate-500">No agents yet.</p>
        )}
      </div>
      <CreateAgentDialog />
    </aside>
  );
}

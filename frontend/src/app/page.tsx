import {
  Activity,
  ArrowUpRight,
  Bot,
  GitBranch,
  Plus,
  Settings,
  Cpu,
  LayoutGrid,
  Box,
} from "lucide-react";
import Link from "next/link";
import { CreateAgentDialog } from "@/features/agents/create-agent-dialog";

const agents = [
  { name: "Research Analyst", model: "claude-sonnet", tone: "emerald" },
  { name: "Data Synthesizer", model: "gpt-4.1", tone: "blue" },
  { name: "Report Writer", model: "claude-sonnet", tone: "violet" },
];

export default function DashboardPage() {
  return (
    <main className="min-h-screen lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <aside className="flex flex-col border-b border-(--border) bg-(--surface) p-5 lg:min-h-screen lg:border-b-0 lg:border-r">
        <Link className="mb-7 flex items-center gap-3" href="/">
          <span className="grid size-8 place-items-center rounded-md bg-emerald-500/15 text-emerald-400 border">
            <Cpu size={19} />
          </span>
          <span className="block text-lg font-bold tracking-wide">AgentFlow</span>
          <span className="text-xs text-(--muted) bg-slate-700 px-2 py-px rounded-sm font-mono">
            v0.1
          </span>
        </Link>
        <nav className="space-y-0.5 text-sm">
          <Link
            className="flex items-center gap-3 rounded-lg bg-emerald-500/10 px-3 py-2.5 font-medium text-emerald-300"
            href="/"
          >
            <LayoutGrid size={16} /> Dashboard
          </Link>
          <Link
            className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-slate-400 hover:bg-white/5 hover:text-white"
            href="/workflows"
          >
            <GitBranch size={16} /> Workflows
          </Link>
          <Link
            className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-slate-400 hover:bg-white/5 hover:text-white"
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
        <div className="mt-10 flex items-center justify-between">
          <p className="text-[11px] font-semibold uppercase tracking-[.18em] text-slate-300">
            Ready agents
          </p>
          <span className="rounded-md bg-white/5 px-2 py-0.5 text-xs text-slate-400">03</span>
        </div>
        <div className="mt-3 space-y-1">
          {agents.map((agent) => (
            <div key={agent.name} className="flex items-center gap-3 rounded-lg px-3 py-2.5">
              <span className="grid size-8 place-items-center rounded-lg bg-white/5 text-slate-300">
                <Bot size={15} />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-xs font-medium">{agent.name}</span>
                <span className="font-mono text-[10px] text-slate-500">{agent.model}</span>
              </span>
              <span className="ml-auto size-1.5 rounded-full bg-emerald-400" />
            </div>
          ))}
        </div>
        <CreateAgentDialog />
      </aside>

      <section className="min-w-0">
        <header className="flex items-center justify-between border-b border-(--border) px-6 py-4 lg:px-10">
          <div className="text-xs text-slate-500">
            Workspace <span className="px-2">/</span>
            <span className="text-slate-300">Dashboard</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden text-xs text-slate-500 sm:block">All systems operational</span>
            <span className="size-2 rounded-full bg-emerald-400" />
            <button
              aria-label="Settings"
              className="rounded-lg p-2 text-slate-400 hover:bg-white/5"
            >
              <Settings size={17} />
            </button>
          </div>
        </header>
        <div className="mx-auto max-w-360 p-6 lg:p-10">
          <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-[.2em] text-emerald-400">
                Orchestration center
              </p>
              <h1 className="text-3xl font-semibold tracking-tight">Good morning.</h1>
              <p className="mt-2 text-sm text-slate-400">
                Build a workflow or monitor your agents in one place.
              </p>
            </div>
            <button className="flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400">
              <Plus size={16} /> New workflow
            </button>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            {[
              {
                label: "Active runs",
                value: "0",
                hint: "No workflows running",
                icon: Activity,
              },
              {
                label: "Available agents",
                value: "03",
                hint: "Ready to orchestrate",
                icon: Bot,
              },
              {
                label: "Workflows",
                value: "0",
                hint: "Create your first workflow",
                icon: GitBranch,
              },
            ].map(({ label, value, hint, icon: Icon }) => (
              <article
                key={label}
                className="rounded-xl border border-(--border) bg-(--surface) p-5"
              >
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span>{label}</span>
                  <Icon size={16} />
                </div>
                <div className="mt-5 text-3xl font-semibold tracking-tight">{value}</div>
                <p className="mt-1 text-xs text-slate-500">{hint}</p>
              </article>
            ))}
          </div>
          <div className="mt-8 grid gap-5 xl:grid-cols-[minmax(0,1.6fr)_minmax(300px,1fr)]">
            <section className="overflow-hidden rounded-xl border border-(--border) bg-(--surface)">
              <div className="flex items-center justify-between border-b border-(--border) px-5 py-4">
                <div>
                  <h2 className="text-sm font-semibold">Recent runs</h2>
                  <p className="mt-1 text-xs text-slate-500">Execution history and live status</p>
                </div>
                <a
                  href="/runs"
                  className="flex items-center gap-1 text-xs text-slate-400 hover:text-white"
                >
                  View all <ArrowUpRight size={13} />
                </a>
              </div>
              <div className="grid min-h-64 place-items-center p-8 text-center">
                <div>
                  <span className="mx-auto grid size-11 place-items-center rounded-xl bg-white/5 text-slate-500">
                    <Activity size={19} />
                  </span>
                  <h3 className="mt-4 text-sm font-medium">No runs yet</h3>
                  <p className="mt-1 max-w-xs text-xs leading-5 text-slate-500">
                    Once you launch a workflow, its progress and results will appear here.
                  </p>
                  <button className="mt-4 text-xs font-medium text-emerald-400 hover:text-emerald-300">
                    Create a workflow <span aria-hidden="true">→</span>
                  </button>
                </div>
              </div>
            </section>
            <section className="rounded-xl border border-(--border) bg-(--surface)">
              <div className="border-b border-(--border) px-5 py-4">
                <h2 className="text-sm font-semibold">Quick start</h2>
                <p className="mt-1 text-xs text-slate-500">Set up your orchestration workspace</p>
              </div>
              <div className="space-y-3 p-4">
                <QuickStart
                  icon={<Bot size={16} />}
                  title="Configure your agents"
                  description="Define roles, models, and tools"
                />
                <QuickStart
                  icon={<GitBranch size={16} />}
                  title="Design a workflow"
                  description="Connect agents into a pipeline"
                />
                <QuickStart
                  icon={<Activity size={16} />}
                  title="Launch and monitor"
                  description="Review a plan before execution"
                />
              </div>
            </section>
          </div>
          <p className="mt-8 text-center text-[11px] text-slate-600">
            Frontend foundation · API connection will be configured through environment settings
          </p>
        </div>
      </section>
    </main>
  );
}

function QuickStart({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <a
      href="#"
      className="flex items-center gap-3 rounded-lg border border-(--border) p-3 transition hover:border-slate-600 hover:bg-white/2"
    >
      <span className="grid size-8 place-items-center rounded-lg bg-white/5 text-slate-300">
        {icon}
      </span>
      <span className="min-w-0">
        <span className="block text-xs font-medium">{title}</span>
        <span className="mt-1 block text-[11px] text-slate-500">{description}</span>
      </span>
      <ArrowUpRight className="ml-auto text-slate-600" size={14} />
    </a>
  );
}

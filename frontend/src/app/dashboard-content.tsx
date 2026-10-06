"use client";

import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  Bot,
  Check,
  CircleHelp,
  CloudUpload,
  FileText,
  LockKeyhole,
  MoreHorizontal,
  Paperclip,
  Play,
  Sparkles,
  X,
} from "lucide-react";
import { useRef, useState } from "react";
import { Sidebar } from "@/components/sidebar";
import { Textarea } from "@/components/ui/textarea";

const agents = [
  { name: "Repo Analyzer", model: "git.connector", status: "Completed", tone: "emerald" },
  { name: "Code Reviewer", model: "coder.gpt-4", status: "Completed", tone: "emerald" },
  { name: "QA Tester", model: "qa.llama-3", status: "In Progress", tone: "amber" },
  { name: "Doc Compiler", model: "writer.gpt-4", status: "Pending", tone: "slate" },
  { name: "Release Deployer", model: "deploy.prod", status: "Failed", tone: "rose" },
];
const events = [
  [
    "14:02:11",
    "Tool: Git Pull",
    "Cloned repository 'github.com/agentflow/core' branch main",
    "cyan",
  ],
  [
    "14:02:15",
    "Agent: Analyzer",
    "Scanning index files... Found 4 active issues matching tag 'security'",
    "violet",
  ],
  [
    "14:03:02",
    "Status: Complete",
    "Repo Analyzer passed structured payload (482 tokens) to Code Reviewer",
    "emerald",
  ],
  [
    "14:03:05",
    "Agent: Coder",
    "Generating patch recommendations for security warning in auth.ts",
    "violet",
  ],
  [
    "14:03:44",
    "Status: Complete",
    "Code Reviewer completed patches with 94.2% test confidence rating",
    "emerald",
  ],
  [
    "14:03:48",
    "Agent: QA Tester",
    "Spinning up isolated sandbox sandbox_v4. Llama-3 starting execution run...",
    "violet",
  ],
  [
    "14:04:01",
    "Tool: Code Exec",
    "Sandbox environment mounted. Executing `npm run test:unit`...",
    "cyan",
  ],
];

export default function DashboardPage() {
  const [task, setTask] = useState(
    "Analyze current repository issues, write a summary report for the QA tester, run unit tests via code executor, and compile final markdown release notes.",
  );
  const [context, setContext] = useState("");
  const [attachment, setAttachment] = useState("");
  const [contextOpen, setContextOpen] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  function handleFile(file: File | undefined) {
    if (!file || !/\.(txt|md|json)$/i.test(file.name)) return;
    setAttachment(file.name);
    void file.text().then(setContext);
    setContextOpen(true);
  }

  return (
    <main className="min-h-screen bg-[#050816] lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <Sidebar />
      <section className="min-w-0">
        <header className="flex min-h-20 flex-wrap items-center justify-between gap-3 border-b border-(--border) px-6 py-4 lg:px-8">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Orchestration Center</h1>
            <p className="mt-1 text-xs text-slate-400">
              Active Session: <span className="font-mono text-slate-300">wf_78d2a_execution</span>
            </p>
          </div>
          <div className="flex items-center gap-5 text-xs text-slate-300">
            <span className="flex items-center gap-2">
              <i className="size-2 rounded-full bg-emerald-400" />
              Completed: 14
            </span>
            <span className="flex items-center gap-2">
              <i className="size-2 rounded-full bg-amber-400" />
              Active Nodes: 1
            </span>
          </div>
        </header>
        <div className="grid min-h-[calc(100vh-80px)] xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0 space-y-5 p-5 lg:p-6">
            <section className="rounded-xl border border-(--border) bg-(--surface) p-4 lg:p-5">
              <label
                htmlFor="workflow-task"
                className="text-[11px] font-semibold uppercase tracking-wide text-slate-400"
              >
                Workflow task definition
              </label>
              <Textarea
                id="workflow-task"
                value={task}
                onChange={(event) => setTask(event.target.value)}
                placeholder="Describe the task you want your workflow to complete..."
                rows={3}
                className="mt-2.5 min-h-24 w-full resize-y rounded-lg border border-(--border) bg-[#050816] px-3 py-3 text-sm leading-6 text-slate-200 outline-none placeholder:text-slate-600 focus:border-emerald-500/60"
              />
              {contextOpen && (
                <div className="mt-3 rounded-lg border border-(--border) bg-[#080e1d] p-3">
                  <div className="mb-2 flex items-center justify-between text-xs text-slate-400">
                    <span className="flex items-center gap-2">
                      <Paperclip size={13} />
                      Additional context
                    </span>
                    <button
                      onClick={() => setContextOpen(false)}
                      aria-label="Close context"
                      className="rounded p-1 hover:bg-white/5"
                    >
                      <X size={14} />
                    </button>
                  </div>
                  {attachment && (
                    <div className="mb-2 flex items-center gap-2 text-xs text-emerald-300">
                      <FileText size={13} />
                      {attachment}
                      <button
                        aria-label="Remove attachment"
                        onClick={() => {
                          setAttachment("");
                          setContext("");
                        }}
                      >
                        <X size={13} />
                      </button>
                    </div>
                  )}
                  <Textarea
                    value={context}
                    onChange={(event) => setContext(event.target.value)}
                    rows={3}
                    placeholder="Paste context here..."
                    className="w-full resize-y bg-transparent text-sm leading-5 text-slate-300 outline-none placeholder:text-slate-600"
                  />
                </div>
              )}
              <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    ref={fileInput}
                    type="file"
                    accept=".txt,.md,.json,text/plain,text/markdown,application/json"
                    className="hidden"
                    onChange={(event) => handleFile(event.target.files?.[0])}
                  />
                  <button
                    onClick={() => fileInput.current?.click()}
                    className="flex items-center gap-2 rounded-lg border border-dashed border-slate-700 px-3 py-2 text-xs text-slate-400 transition hover:border-slate-500 hover:text-slate-200"
                  >
                    <CloudUpload size={15} />
                    Add context file <span className="text-slate-600">TXT · MD · JSON</span>
                  </button>
                  <button
                    onClick={() => setContextOpen(true)}
                    className="rounded-lg px-2 py-2 text-xs text-slate-400 hover:bg-white/5 hover:text-slate-200"
                  >
                    Paste text
                  </button>
                  {attachment && (
                    <span className="flex items-center gap-1 text-xs text-emerald-300">
                      <Check size={12} />
                      {attachment}
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  className="flex items-center justify-center gap-2 rounded-lg bg-emerald-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400"
                >
                  <Sparkles size={16} />
                  <span>Decompose and Run</span>
                  <Play size={14} />
                </button>
              </div>
            </section>
            <section className="rounded-xl border border-(--border) bg-(--surface) p-4 lg:p-5">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Active execution pipeline
                  </h2>
                  <p className="mt-1 text-[11px] text-slate-600">Demo workflow · sample data</p>
                </div>
                <button
                  aria-label="More pipeline options"
                  className="text-slate-500 hover:text-slate-300"
                >
                  <MoreHorizontal size={18} />
                </button>
              </div>
              <div className="flex gap-2 overflow-x-auto pb-1">
                {agents.map((agent, index) => (
                  <div key={agent.name} className="flex min-w-30.5 flex-1 items-center gap-2">
                    <article
                      className={`min-w-29.5 flex-1 rounded-lg border p-3 ${agent.status === "In Progress" ? "border-blue-500 bg-blue-500/10" : "border-(--border) bg-[#0b1220]"}`}
                    >
                      <h3 className="truncate text-xs font-semibold text-slate-200">
                        {agent.name}
                      </h3>
                      <p className="mt-1 truncate font-mono text-[10px] text-slate-500">
                        {agent.model}
                      </p>
                      <span
                        className={`mt-2 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium ${agent.tone === "emerald" ? "bg-emerald-500/10 text-emerald-400" : agent.tone === "amber" ? "bg-amber-500/15 text-amber-300" : agent.tone === "rose" ? "bg-rose-500/15 text-rose-400" : "bg-slate-700/70 text-slate-400"}`}
                      >
                        <i className="size-1.5 rounded-full bg-current" />
                        {agent.status}
                      </span>
                    </article>
                    {index < agents.length - 1 && (
                      <ArrowRight className="shrink-0 text-slate-700" size={15} />
                    )}
                  </div>
                ))}
              </div>
            </section>
            <section className="flex min-h-97.5 flex-col overflow-hidden rounded-xl border border-(--border) bg-[#050816]">
              <div className="flex items-center justify-between border-b border-(--border) bg-(--surface) px-4 py-3">
                <h2 className="flex items-center gap-2 font-mono text-xs font-semibold tracking-wide text-slate-200">
                  <i className="size-2 rounded-full bg-emerald-400" />
                  LIVE ORCHESTRATION CONSOLE
                </h2>
                <button
                  type="button"
                  className="rounded border border-(--border) px-2 py-1 font-mono text-[10px] text-slate-400 hover:text-white"
                >
                  Clear
                </button>
              </div>
              <div
                aria-label="Sample orchestration events"
                className="space-y-3 overflow-auto p-4 font-mono text-[11px] leading-5"
              >
                {events.map(([time, tag, message, tone]) => (
                  <div key={time} className="grid grid-cols-[58px_98px_minmax(0,1fr)] gap-2">
                    <span className="text-slate-600">{time}</span>
                    <span
                      className={`w-fit self-start rounded px-1.5 py-0.5 text-[10px] leading-4 ${tone === "cyan" ? "bg-cyan-500/15 text-cyan-300" : tone === "violet" ? "bg-violet-500/20 text-violet-300" : "bg-emerald-500/15 text-emerald-300"}`}
                    >
                      {tag}
                    </span>
                    <span className="text-slate-300">{message}</span>
                  </div>
                ))}
                <p className="mt-5 flex items-center gap-2 text-emerald-400">
                  <ArrowDownToLine size={14} />
                  Live stream running... Listening to orchestrator events
                </p>
              </div>
            </section>
          </div>
          <aside className="flex flex-col gap-3 border-t border-(--border) bg-[#080e1d] p-4 xl:border-l xl:border-t-0">
            <h2 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Active agent inspector
            </h2>
            <section className="flex items-center gap-3 rounded-lg border border-(--border) bg-(--surface) p-3">
              <span className="grid size-10 place-items-center rounded-full border border-amber-500 bg-amber-950/70 text-amber-400">
                <Bot size={20} />
              </span>
              <div>
                <h3 className="text-sm font-semibold">QA Tester</h3>
                <p className="font-mono text-[10px] text-amber-400">running.llama-3-70b</p>
              </div>
            </section>
            <section className="py-1">
              <div className="mb-2 flex justify-between text-xs">
                <span className="text-slate-400">Running Unit Tests</span>
                <span className="font-mono text-amber-300">64%</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
                <div className="h-full w-[64%] bg-amber-400" />
              </div>
            </section>
            <section className="rounded-lg border border-(--border) bg-(--surface) p-3">
              <h3 className="mb-2 text-[10px] font-semibold uppercase text-slate-400">
                Current step
              </h3>
              <p className="font-mono text-xs leading-[1.4] text-slate-300">
                Sandbox container mount #4: Verifying user authorization schemas in integration
                tests.
              </p>
            </section>
            <section className="rounded-lg border border-(--border) bg-(--surface) p-3">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-[10px] font-semibold uppercase text-slate-400">
                  Input context
                </h3>
                <button aria-label="Help about input context" className="text-slate-600">
                  <CircleHelp size={13} />
                </button>
              </div>
              <pre className="overflow-x-auto rounded bg-[#050816] p-2.5 font-mono text-[10px] leading-4 text-cyan-300">
                {
                  '{\n  "test_target": "auth.ts",\n  "mock_db": true,\n  "depth": "comprehensive",\n  "concurrency": 4\n}'
                }
              </pre>
            </section>
            <section className="rounded-lg border border-(--border) bg-(--surface) p-3">
              <div className="flex items-center justify-between">
                <h3 className="text-[10px] font-semibold uppercase text-slate-400">Token usage</h3>
                <span className="font-mono text-[11px] text-slate-300">12,402 / 32,000</span>
              </div>
              <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-slate-800">
                <span className="w-[41%] bg-violet-400" />
                <span className="w-[13%] bg-cyan-400" />
              </div>
              <div className="mt-2 flex gap-3 text-[10px] text-slate-500">
                <span className="text-violet-300">● Prompt (8.9k)</span>
                <span className="text-cyan-300">● Completion (3.5k)</span>
              </div>
            </section>
            <section className="mt-auto rounded-lg border border-(--border) bg-(--surface) p-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-semibold">Final report</h3>
                <LockKeyhole size={14} className="text-slate-600" />
              </div>
              <p className="mt-2 text-xs leading-5 text-slate-500">
                The workflow summary artifact is locked and will be generated automatically once the
                Doc Compiler agent completes the stack.
              </p>
            </section>
            <p className="flex items-center justify-center gap-1 text-[10px] text-slate-600">
              <Activity size={12} />
              All inspector values are sample data
            </p>
          </aside>
        </div>
      </section>
    </main>
  );
}

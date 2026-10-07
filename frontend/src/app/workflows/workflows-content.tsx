"use client";

import { useMemo, useRef, useState } from "react";
import {
  addEdge,
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { GitBranch, LoaderCircle, Pencil, Plus, Save, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger } from "@/components/ui/select";
import { Sidebar } from "@/components/sidebar";
import { useAgents } from "@/features/agents/queries";
import {
  useDeleteWorkflow,
  useSaveWorkflow,
  useWorkflows,
  type Workflow,
  type WorkflowInput,
  type WorkflowType,
} from "@/features/workflows/queries";

type AgentNodeData = {
  agentId: string;
  label: string;
  role: string;
  model: string;
  step: number;
  inputTransform: string;
};
type AgentNode = Node<AgentNodeData>;

function inferType(nodes: AgentNode[], edges: Edge[]): WorkflowType {
  const ordered = [...nodes].sort((left, right) => left.data.step - right.data.step);
  const incoming = new Map(
    ordered.map((node) => [
      node.data.step,
      edges
        .filter((edge) => edge.target === node.id)
        .map((edge) => Number(edge.source))
        .sort((left, right) => left - right),
    ]),
  );
  if (
    ordered.every(
      (node, index) =>
        JSON.stringify(incoming.get(node.data.step)) ===
        JSON.stringify(index === 0 ? [] : [ordered[index - 1].data.step]),
    )
  )
    return "sequential";
  const aggregators = [...incoming].filter(([, dependencies]) => dependencies.length > 0);
  if (
    aggregators.length <= 1 &&
    (aggregators.length === 0 ||
      (aggregators[0][1].length === ordered.length - 1 &&
        aggregators[0][1].every((step) => step !== aggregators[0][0])))
  )
    return "parallel";
  return "hybrid";
}

function graphErrors(nodes: AgentNode[], edges: Edge[]): string[] {
  const errors: string[] = [];
  if (!nodes.length) errors.push("Add at least one agent to the workflow.");
  if (nodes.length > 1) {
    const connected = new Set<string>([nodes[0].id]);
    let changed = true;
    while (changed) {
      changed = false;
      edges.forEach((edge) => {
        if (connected.has(edge.source) && !connected.has(edge.target)) {
          connected.add(edge.target);
          changed = true;
        }
        if (connected.has(edge.target) && !connected.has(edge.source)) {
          connected.add(edge.source);
          changed = true;
        }
      });
    }
    if (connected.size !== nodes.length)
      errors.push("Every node must be connected to the workflow.");
  }
  const remaining = new Map(
    nodes.map((node) => [node.id, edges.filter((edge) => edge.target === node.id).length]),
  );
  const ready = [...remaining].filter(([, count]) => count === 0).map(([id]) => id);
  let visited = 0;
  while (ready.length) {
    const id = ready.pop();
    if (!id) continue;
    visited += 1;
    edges
      .filter((edge) => edge.source === id)
      .forEach((edge) => {
        const count = (remaining.get(edge.target) ?? 0) - 1;
        remaining.set(edge.target, count);
        if (count === 0) ready.push(edge.target);
      });
  }
  if (visited !== nodes.length) errors.push("The graph contains a cycle.");
  return errors;
}

export default function WorkflowsContent() {
  const workflowsQuery = useWorkflows();
  const agentsQuery = useAgents();
  const saveMutation = useSaveWorkflow();
  const deleteMutation = useDeleteWorkflow();
  const [editing, setEditing] = useState<Workflow | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [nodes, setNodes, onNodesChange] = useNodesState<AgentNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const undoStack = useRef<Array<{ nodes: AgentNode[]; edges: Edge[] }>>([]);
  const redoStack = useRef<Array<{ nodes: AgentNode[]; edges: Edge[] }>>([]);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);
  function rememberGraph() {
    undoStack.current.push({ nodes, edges });
    if (undoStack.current.length > 50) undoStack.current.shift();
    redoStack.current = [];
    setCanUndo(true);
    setCanRedo(false);
  }
  function undoGraph() {
    const previous = undoStack.current.pop();
    if (!previous) return;
    redoStack.current.push({ nodes, edges });
    setNodes(previous.nodes);
    setEdges(previous.edges);
    setCanUndo(undoStack.current.length > 0);
    setCanRedo(true);
  }
  function redoGraph() {
    const next = redoStack.current.pop();
    if (!next) return;
    undoStack.current.push({ nodes, edges });
    setNodes(next.nodes);
    setEdges(next.edges);
    setCanUndo(true);
    setCanRedo(redoStack.current.length > 0);
  }
  function autoLayout() {
    rememberGraph();
    const remaining = new Map(
      nodes.map((node) => [node.id, edges.filter((edge) => edge.target === node.id).length]),
    );
    const levels = new Map<string, number>();
    const queue = [...remaining].filter(([, count]) => count === 0).map(([id]) => id);
    while (queue.length) {
      const id = queue.shift();
      if (!id) continue;
      for (const edge of edges.filter((item) => item.source === id)) {
        levels.set(edge.target, Math.max(levels.get(edge.target) ?? 0, (levels.get(id) ?? 0) + 1));
        const count = (remaining.get(edge.target) ?? 1) - 1;
        remaining.set(edge.target, count);
        if (count === 0) queue.push(edge.target);
      }
    }
    const offsets = new Map<number, number>();
    setNodes(
      nodes.map((node) => {
        const level = levels.get(node.id) ?? 0;
        const row = offsets.get(level) ?? 0;
        offsets.set(level, row + 1);
        return { ...node, position: { x: 90 + level * 280, y: 80 + row * 170 } };
      }),
    );
  }
  const agents = agentsQuery.data?.items ?? [];
  const selected = nodes.find((node) => node.id === selectedId);
  const errors = useMemo(() => graphErrors(nodes, edges), [nodes, edges]);
  const executionType = useMemo(() => inferType(nodes, edges), [nodes, edges]);
  const onConnect = (connection: Connection) => {
    rememberGraph();
    setEdges((current) => addEdge(connection, current));
  };

  function openEditor(workflow?: Workflow) {
    setEditorOpen(true);
    setEditing(workflow ?? null);
    setTitle(workflow?.title ?? "");
    const agentMap = new Map(agents.map((agent) => [agent.id, agent]));
    const nextNodes: AgentNode[] = (workflow?.steps ?? []).map((step, index) => {
      const agent = agentMap.get(step.agent_id);
      return {
        id: String(step.step_number),
        type: "default",
        position: workflow?.graph_layout[String(step.step_number)] ?? {
          x: 80 + (index % 3) * 260,
          y: 80 + Math.floor(index / 3) * 170,
        },
        data: {
          agentId: step.agent_id,
          label: agent?.name ?? "Unknown agent",
          role: agent?.role ?? "",
          model: agent?.model ?? "",
          step: step.step_number,
          inputTransform: step.input_transform,
        },
      };
    });
    setNodes(nextNodes);
    setEdges(
      (workflow?.steps ?? []).flatMap((step) =>
        step.depends_on.map((dep) => ({
          id: `${dep}-${step.step_number}`,
          source: String(dep),
          target: String(step.step_number),
          type: "smoothstep",
          animated: false,
        })),
      ),
    );
    setSelectedId(null);
    undoStack.current = [];
    redoStack.current = [];
    setCanUndo(false);
    setCanRedo(false);
    setNotice("");
  }

  function addAgent(agentId: string) {
    const agent = agents.find((item) => item.id === agentId);
    if (!agent) return;
    const step = Math.max(0, ...nodes.map((node) => node.data.step)) + 1;
    rememberGraph();
    setNodes((current) => [
      ...current,
      {
        id: String(step),
        type: "default",
        position: { x: 100 + ((step - 1) % 3) * 260, y: 100 + Math.floor((step - 1) / 3) * 170 },
        data: {
          agentId,
          label: agent.name,
          role: agent.role,
          model: agent.model,
          step,
          inputTransform: "{{subtask}}",
        },
      },
    ]);
  }

  async function save() {
    if (!title.trim() || errors.length) return;
    const payload: WorkflowInput & { id?: string } = {
      ...(editing ? { id: editing.id } : {}),
      title: title.trim(),
      execution_type: executionType,
      steps: nodes.map((node) => ({
        step_number: node.data.step,
        agent_id: node.data.agentId,
        depends_on: edges
          .filter((edge) => edge.target === node.id)
          .map((edge) => Number(edge.source))
          .sort((a, b) => a - b),
        input_transform: node.data.inputTransform,
      })),
      graph_layout: Object.fromEntries(nodes.map((node) => [node.id, node.position])),
    };
    try {
      await saveMutation.mutateAsync(payload);
      setEditorOpen(false);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not save workflow.");
    }
  }

  return (
    <main className="min-h-screen lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <Sidebar />
      <section className="min-w-0">
        <header className="flex min-h-20 flex-wrap items-center justify-between gap-3 border-b border-border px-6 py-4 lg:px-8">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Workflows</h1>
            <p className="mt-1 text-xs text-slate-400">
              Orchestration design · Compose agents into sequential, parallel, or hybrid execution
              graphs.
            </p>
          </div>
          <Button onClick={() => openEditor()} disabled={!agents.length}>
            <Plus size={16} /> New workflow
          </Button>
        </header>
        <div className="mx-auto max-w-360 p-6 lg:p-10">
          {workflowsQuery.isLoading && (
            <div className="grid min-h-52 place-items-center">
              <LoaderCircle className="animate-spin text-slate-400" />
            </div>
          )}
          {workflowsQuery.isError && (
            <div
              role="alert"
              className="rounded-xl border border-rose-900/60 p-5 text-sm text-rose-300"
            >
              Could not load workflows.{" "}
              <button onClick={() => void workflowsQuery.refetch()} className="underline">
                Try again
              </button>
            </div>
          )}
          {agentsQuery.isSuccess && agents.length === 0 && (
            <p className="mb-4 rounded-lg border border-border p-4 text-sm text-slate-400">
              Create an agent before building a workflow.
            </p>
          )}
          {!workflowsQuery.isLoading &&
            workflowsQuery.isSuccess &&
            workflowsQuery.data.items.length === 0 && (
              <div className="grid min-h-64 place-items-center rounded-xl border border-dashed border-border bg-(--surface) p-8 text-center">
                <div>
                  <GitBranch className="mx-auto text-emerald-400" />
                  <h2 className="mt-4 font-semibold">No workflows yet</h2>
                  <p className="mt-2 text-sm text-slate-400">
                    Create a workflow to define how your agents collaborate.
                  </p>
                </div>
              </div>
            )}
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {(workflowsQuery.data?.items ?? []).map((workflow) => (
              <article
                key={workflow.id}
                className="rounded-xl border border-border bg-(--surface) p-5"
              >
                <span className="w-full text-left flex flex-col">
                  <p className="font-semibold">{workflow.title}</p>
                  <p className="mt-2 text-xs uppercase tracking-wider text-emerald-400">
                    {workflow.execution_type}
                  </p>
                  <p className="mt-3 text-sm text-slate-400">
                    {workflow.steps.length} steps · updated{" "}
                    {new Date(workflow.updated_at).toLocaleDateString()}
                  </p>
                </span>
                <footer className="mt-4 flex justify-end gap-2 border-t border-border pt-3">
                  <Button onClick={() => openEditor(workflow)} size="icon">
                    <Pencil size={18} />
                  </Button>
                  <Button
                    aria-label={`Delete ${workflow.title}`}
                    variant="destructive"
                    size="icon"
                    onClick={() => {
                      if (window.confirm(`Delete "${workflow.title}"?`))
                        void deleteMutation.mutateAsync(workflow.id);
                    }}
                  >
                    <Trash2 size={18} />
                  </Button>
                </footer>
              </article>
            ))}
          </div>
        </div>
      </section>
      {editorOpen && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/80 p-3 sm:p-6">
          <section
            className="flex h-[92vh] w-full max-w-7xl flex-col overflow-hidden rounded-xl border border-border bg-(--surface)"
            role="dialog"
            aria-modal="true"
            aria-labelledby="workflow-editor-title"
          >
            <header className="flex flex-wrap items-center gap-3 border-b border-border p-4">
              <Input
                id="workflow-title"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Workflow title"
                className="min-w-40 flex-1 rounded-md border border-border bg-slate-950 px-3 py-2 text-sm"
              />
              <span className="rounded-md bg-emerald-500/10 px-3 py-2 text-xs font-medium uppercase text-emerald-300">
                {executionType}
              </span>
              <Button size="sm" variant="secondary" disabled={!canUndo} onClick={undoGraph}>
                Undo
              </Button>
              <Button size="sm" variant="secondary" disabled={!canRedo} onClick={redoGraph}>
                Redo
              </Button>
              <Button size="sm" variant="secondary" onClick={autoLayout}>
                Auto layout
              </Button>
              <Button
                onClick={() => setEditorOpen(false)}
                aria-label="Close editor"
                size="icon"
                variant="ghost"
              >
                <X size={18} />
              </Button>
            </header>
            <div className="flex min-h-0 flex-1">
              <aside className="w-56 shrink-0 overflow-y-auto border-r border-border p-3">
                <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Agent palette
                </p>
                {agents.map((agent) => (
                  <Button
                    key={agent.id}
                    variant="ghost"
                    onClick={() => addAgent(agent.id)}
                    className="mb-2 w-full rounded-lg border border-border p-3 text-left hover:border-emerald-500/50"
                  >
                    <span className="block truncate text-xs font-medium">{agent.name}</span>
                    <span className="mt-1 block truncate font-mono text-[10px] text-slate-500">
                      {agent.model}
                    </span>
                  </Button>
                ))}
                <div className="mt-4 border-t border-border pt-3">
                  <label htmlFor="preset" className="text-xs text-slate-400">
                    Arrange preset
                  </label>
                  <Select
                    onValueChange={(value) => {
                      const kind = value as WorkflowType;
                      rememberGraph();
                      setEdges([]);
                      setNodes((current) =>
                        current.map((node, index) => ({
                          ...node,
                          position: {
                            x: 100 + (kind === "sequential" ? 0 : (index % 3) * 240),
                            y: 70 + index * (kind === "sequential" ? 130 : 180),
                          },
                        })),
                      );
                      if (kind === "sequential")
                        setEdges(
                          nodes.slice(1).map((node, index) => ({
                            id: `${nodes[index].id}-${node.id}`,
                            source: nodes[index].id,
                            target: node.id,
                          })),
                        );
                      else if (kind === "parallel" && nodes.length > 1) {
                        const final = nodes[nodes.length - 1];
                        setEdges(
                          nodes.slice(0, -1).map((node) => ({
                            id: `${node.id}-${final.id}`,
                            source: node.id,
                            target: final.id,
                          })),
                        );
                      }
                    }}
                  >
                    <SelectTrigger id="preset" aria-label="Arrange preset" className="mt-2 w-full rounded-md border border-border bg-slate-950 px-2 py-2 text-xs">Hybrid graph</SelectTrigger>
                    <SelectContent>
                      <SelectItem value="hybrid">Hybrid graph</SelectItem>
                      <SelectItem value="sequential">Sequential chain</SelectItem>
                      <SelectItem value="parallel">Parallel + aggregator</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </aside>
              <div className="workflow-canvas min-w-0 flex-1 bg-slate-950">
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  onNodesChange={onNodesChange}
                  onEdgesChange={onEdgesChange}
                  onConnect={onConnect}
                  onNodeClick={(_, node) => setSelectedId(node.id)}
                  fitView
                >
                  <Background color="var(--border)" />
                  <Controls />
                  <MiniMap pannable zoomable style={{ width: 140, height: 100 }} />
                </ReactFlow>
              </div>
              <aside className="w-64 shrink-0 overflow-y-auto border-l border-border p-4">
                <p className="mb-4 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Node properties
                </p>
                {selected ? (
                  <>
                    <p className="truncate text-sm font-medium">{selected.data.label}</p>
                    <p className="mt-1 text-xs text-slate-500">
                      Step {selected.data.step} · {selected.data.model}
                    </p>
                    <label htmlFor="input-transform" className="mt-5 block text-xs text-slate-400">
                      Input transform
                    </label>
                    <textarea
                      id="input-transform"
                      key={`${editing?.id ?? "new"}-${selected.id}`}
                      value={selected.data.inputTransform}
                      onChange={(event) =>
                        setNodes((current) =>
                          current.map((node) =>
                            node.id === selected.id
                              ? {
                                  ...node,
                                  data: { ...node.data, inputTransform: event.target.value },
                                }
                              : node,
                          ),
                        )
                      }
                      rows={8}
                      className="mt-2 w-full resize-y rounded-md border border-border bg-slate-950 p-2 font-mono text-xs"
                    />
                    <p className="mt-2 text-[10px] text-slate-500">
                      Available: task, subtask, context, steps.N.output
                    </p>
                    <Button
                      variant="ghost"
                      onClick={() => {
                        setNodes((current) => current.filter((node) => node.id !== selected.id));
                        setEdges((current) =>
                          current.filter(
                            (edge) => edge.source !== selected.id && edge.target !== selected.id,
                          ),
                        );
                        setSelectedId(null);
                      }}
                      className="mt-5 flex items-center gap-2 text-xs text-rose-300"
                    >
                      <Trash2 size={13} /> Remove node
                    </Button>
                  </>
                ) : (
                  <p className="text-xs text-slate-500">
                    Select a graph node to edit its input template.
                  </p>
                )}
                <div className="mt-6 border-t border-border pt-4">
                  <p className="text-xs font-semibold text-slate-400">Validation</p>
                  {errors.length ? (
                    <ul className="mt-2 list-inside list-disc space-y-1 text-xs text-rose-300">
                      {errors.map((error) => (
                        <li key={error}>{error}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-2 text-xs text-emerald-300">Graph is valid.</p>
                  )}
                </div>
              </aside>
            </div>
            {notice && (
              <p
                role="alert"
                className="border-t border-rose-900/60 px-4 py-2 text-sm text-rose-300"
              >
                {notice}
              </p>
            )}
            <footer className="flex justify-end gap-2 border-t border-border p-3">
              <Button
                variant="secondary"
                onClick={() => setEditorOpen(false)}
                className="rounded-md border border-border px-4 py-2 text-sm text-slate-300"
              >
                Cancel
              </Button>
              <Button
                variant="default"
                onClick={() => void save()}
                disabled={!title.trim() || errors.length > 0 || saveMutation.isPending}
                className="flex items-center gap-2 rounded-md bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 disabled:opacity-40"
              >
                {saveMutation.isPending ? (
                  <LoaderCircle size={15} className="animate-spin" />
                ) : (
                  <Save size={15} />
                )}{" "}
                Save workflow
              </Button>
            </footer>
          </section>
        </div>
      )}
    </main>
  );
}
